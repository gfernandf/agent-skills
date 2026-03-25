from __future__ import annotations

import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, List

from runtime.errors import InvalidSkillSpecError
from runtime.metrics import METRICS

_DEFAULT_MAX_WORKERS = 8


class _StateLock:
    """
    Sharded lock that serializes mutations to ExecutionState by namespace.

    Instead of a single global lock, writes to ``vars``, ``outputs``,
    ``working``, and ``events`` each use their own lock.  This reduces
    contention when parallel steps write to different namespaces.

    The context-manager interface (``with state_lock:``) still acquires
    ALL shards for backward compatibility — used as the default path.
    Fine-grained callers can use ``lock_for(namespace)`` instead.
    """

    _NAMESPACES = ("vars", "outputs", "working", "events")

    def __init__(self) -> None:
        self._locks = {ns: threading.Lock() for ns in self._NAMESPACES}
        self._global = threading.Lock()

    # ── Global lock (backward-compatible) ─────────────────────────
    def __enter__(self):
        self._global.acquire()
        return self

    def __exit__(self, *exc):
        self._global.release()

    # ── Per-namespace lock ────────────────────────────────────────
    def lock_for(self, namespace: str) -> threading.Lock:
        """Return the lock for a specific namespace, falling back to global."""
        return self._locks.get(namespace, self._global)

    @staticmethod
    def noop():
        """No-op lock for sequential execution contexts."""
        return _NoopLock()


class _NoopLock:
    """No-op context manager — used when no parallelism is active."""
    def __enter__(self):
        return self
    def __exit__(self, *exc):
        pass


class Scheduler:
    """
    DAG-based step scheduler with backward-compatible implicit dependencies.

    Dependency rules:
      1. If a step declares ``config.depends_on``, those are its explicit deps.
      2. If a step does NOT declare ``depends_on``, it implicitly depends on the
         immediately preceding step in declared order (preserves v1 sequential
         semantics for all existing skills).

    Thread safety:
      All mutations to shared ExecutionState happen inside the step_executor
      callback, which the engine already serializes through apply_step_output
      and emit_event.  The scheduler wraps each step_executor call so that
      state writes are protected by ``state_lock``.
    """

    def __init__(self, max_workers: int | None = None, storage_manager=None):
        if max_workers is not None:
            self.max_workers = max_workers
        else:
            env_val = os.getenv("AGENT_SKILLS_MAX_WORKERS", "")
            try:
                self.max_workers = int(env_val) if env_val else _DEFAULT_MAX_WORKERS
            except ValueError:
                self.max_workers = _DEFAULT_MAX_WORKERS
        self.storage_manager = storage_manager

    def schedule(
        self,
        plan: List[Any],
        context,
        step_executor: Callable,
        trace_callback=None,
    ) -> List[Any]:
        if not plan:
            return []

        step_map = {step.id: step for step in plan}
        step_order = [step.id for step in plan]

        # --- Build dependency graph ---
        dependencies: dict[str, set[str]] = {}
        for idx, step in enumerate(plan):
            explicit = step.config.get("depends_on")
            if explicit is not None:
                dependencies[step.id] = set(explicit)
            elif idx == 0:
                dependencies[step.id] = set()
            else:
                # Implicit: depend on immediately preceding step
                dependencies[step.id] = {step_order[idx - 1]}

        # Validate references
        skill_id = getattr(getattr(context, "state", None), "skill_id", None)
        for step_id, deps in dependencies.items():
            for dep in deps:
                if dep not in step_map:
                    raise InvalidSkillSpecError(
                        f"Step '{step_id}' depends on unknown step '{dep}'.",
                        skill_id=skill_id,
                    )

        # Detect circular dependencies (Kahn's algorithm)
        in_degree = {sid: len(deps) for sid, deps in dependencies.items()}
        reverse: dict[str, list[str]] = {sid: [] for sid in step_map}
        for sid, deps in dependencies.items():
            for dep in deps:
                reverse[dep].append(sid)
        queue = [sid for sid, deg in in_degree.items() if deg == 0]
        visited = 0
        while queue:
            node = queue.pop()
            visited += 1
            for dependent in reverse[node]:
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)
        if visited < len(step_map):
            cycle_members = sorted(
                sid for sid, deg in in_degree.items() if deg > 0
            )
            raise InvalidSkillSpecError(
                "Circular dependency detected among steps: "
                + ", ".join(cycle_members),
                skill_id=skill_id,
            )

        # --- Execution loop ---
        state_lock = _StateLock()
        # Attach lock to context so engine can use it around state mutations
        context.state_lock = state_lock
        completed: set[str] = set()
        failed: set[str] = set()
        results: list = []
        running: set[str] = set()

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures: dict = {}
            while len(completed) + len(failed) < len(plan):
                ready = [
                    sid for sid, deps in dependencies.items()
                    if sid not in completed
                    and sid not in failed
                    and sid not in running
                    and deps.issubset(completed)
                    and not deps.intersection(failed)
                ]
                for sid in ready:
                    step = step_map[sid]
                    future = executor.submit(
                        step_executor, step, context.state.skill_id,
                        context, trace_callback,
                    )
                    futures[future] = sid
                    running.add(sid)

                # Track when ready steps are queued but the pool is at capacity
                if ready and len(running) >= self.max_workers:
                    METRICS.inc("scheduler.pool_saturated")

                if not futures:
                    unresolved = [
                        sid for sid in step_order
                        if sid not in completed and sid not in failed
                    ]
                    if not unresolved:
                        break
                    # Check which unresolved steps are blocked by failures
                    blocked = [
                        sid for sid in unresolved
                        if dependencies[sid].intersection(failed)
                    ]
                    if blocked:
                        if getattr(context.options, "fail_fast", True):
                            raise RuntimeError(
                                "Blocked steps due to failed dependencies: "
                                + ", ".join(sorted(blocked))
                            )
                        # fail_fast=False: mark blocked steps as skipped
                        from runtime.models import StepResult as SR
                        for sid in blocked:
                            skip = SR(
                                step_id=sid,
                                uses=step_map[sid].uses,
                                status="skipped",
                                resolved_input={},
                                produced_output=None,
                                error_message="Skipped: dependency failed",
                                started_at=None,
                                finished_at=None,
                            )
                            results.append(skip)
                            failed.add(sid)
                        continue
                    raise RuntimeError(
                        "Execution deadlock detected. Check circular or "
                        "unsatisfied dependencies: "
                        + ", ".join(sorted(unresolved))
                    )

                next(as_completed(futures))
                for future in list(futures):
                    if future.done():
                        sid = futures.pop(future)
                        running.discard(sid)
                        try:
                            result = future.result()
                        except Exception as exc:
                            # Safety and gate errors must propagate immediately
                            # (they are deliberate execution blocks, not failures).
                            from runtime.errors import (
                                SafetyTrustLevelError,
                                SafetyGateFailedError,
                                SafetyConfirmationRequiredError,
                                GateExecutionError,
                            )
                            if isinstance(exc, (
                                SafetyTrustLevelError,
                                SafetyGateFailedError,
                                SafetyConfirmationRequiredError,
                                GateExecutionError,
                            )):
                                raise
                            # Step executor raised an unhandled exception
                            # (e.g. timeout). Create a failed
                            # StepResult so the scheduler can continue or
                            # abort cleanly instead of deadlocking.
                            from runtime.models import StepResult as SR
                            result = SR(
                                step_id=sid,
                                uses=step_map[sid].uses,
                                status="failed",
                                resolved_input={},
                                produced_output=None,
                                error_message=str(exc),
                                started_at=None,
                                finished_at=None,
                            )
                        results.append(result)
                        if result.status == "completed":
                            completed.add(sid)
                        else:
                            failed.add(sid)
                            if getattr(context.options, "fail_fast", True):
                                for f in futures:
                                    f.cancel()
                                return results
        return results

"""In-memory run store for async execution tracking.

Stores run metadata in a thread-safe dict.  Optionally persists completed
runs to a JSONL file for post-mortem analysis.

Supports pluggable backends via the RunStoreBackend protocol for production
deployments (PostgreSQL, Redis, etc.).

This is NOT a replacement for the audit system — it tracks async run
lifecycle for the HTTP client.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from runtime.run_lifecycle import (
    RUN_STATUSES,
    RUN_STATUS_CANCELED,
    RUN_STATUS_COMPLETED,
    RUN_STATUS_FAILED,
    RUN_STATUS_PENDING,
    RUN_STATUS_REPLAYING,
    RUN_STATUS_RUNNING,
    TERMINAL_RUN_STATUSES,
    RunStateMachine,
)


# ── Pluggable backend protocol ────────────────────────────────────


@runtime_checkable
class RunStoreBackend(Protocol):
    """Interface for persistent run store backends.

    Implement this protocol to back the RunStore with PostgreSQL, Redis,
    or any other persistent storage. The default in-memory backend is used
    when no external backend is provided.

    Example PostgreSQL implementation::

        class PostgresRunStoreBackend:
            def __init__(self, dsn: str): ...
            def save_run(self, run: dict[str, Any]) -> None: ...
            def load_run(self, run_id: str) -> dict[str, Any] | None: ...
            def list_runs(self, *, limit: int = 100) -> list[dict[str, Any]]: ...
            def delete_run(self, run_id: str) -> bool: ...
    """

    def save_run(self, run: dict[str, Any]) -> None: ...
    def load_run(self, run_id: str) -> dict[str, Any] | None: ...
    def list_runs(self, *, limit: int = 100) -> list[dict[str, Any]]: ...
    def delete_run(self, run_id: str) -> bool: ...


class RunStoreV2:
    """Thread-safe canonical run store with lifecycle-aware transitions."""

    def __init__(
        self,
        *,
        persist_path: Path | None = None,
        max_runs: int = 100,
        backend: RunStoreBackend | None = None,
    ) -> None:
        self._lock = threading.Lock()
        self._runs: dict[str, dict[str, Any]] = {}
        self._order: list[str] = []
        self._max_runs = max(1, max_runs)
        self._persist_path = persist_path
        self._backend = backend
        self._state_machine = RunStateMachine()

    def create_run_record(
        self,
        *,
        run_id: str,
        skill_id: str,
        trace_id: str | None = None,
        thread_id: str | None = None,
        session_id: str | None = None,
        status: str = RUN_STATUS_PENDING,
        skill_version: str | None = None,
        checkpoint_head: str | None = None,
        resume_from_checkpoint_id: str | None = None,
        current_step_id: str | None = None,
        tenant_id: str | None = None,
        environment: str | None = None,
        policy_snapshot_id: str | None = None,
        versions: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self._state_machine.is_valid_status(status):
            raise ValueError(f"Invalid run status '{status}'.")

        now = _utc_now_iso()
        run = {
            "run_id": run_id,
            "thread_id": thread_id,
            "session_id": session_id,
            "skill_id": skill_id,
            "skill_version": skill_version,
            "status": status,
            "trace_id": trace_id,
            "created_at": now,
            "started_at": now if status in {RUN_STATUS_RUNNING, RUN_STATUS_REPLAYING} else None,
            "finished_at": now if status in TERMINAL_RUN_STATUSES else None,
            "current_step_id": current_step_id,
            "checkpoint_head": checkpoint_head,
            "resume_from_checkpoint_id": resume_from_checkpoint_id,
            "tenant_id": tenant_id,
            "environment": environment,
            "policy_snapshot_id": policy_snapshot_id,
            "versions": versions or {},
            "metadata": metadata or {},
            # Legacy-compatible fields
            "result": None,
            "error": None,
        }

        with self._lock:
            self._runs[run_id] = run
            self._order.append(run_id)
            self._evict()

        self._save_backend(run)
        return dict(run)

    def create_run(
        self,
        run_id: str,
        skill_id: str,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        # Legacy compatibility entrypoint: starts in running state.
        return self.create_run_record(
            run_id=run_id,
            skill_id=skill_id,
            trace_id=trace_id,
            status=RUN_STATUS_RUNNING,
        )

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            run = self._runs.get(run_id)
            if run is not None:
                return dict(run)
        # Fallback to backend if not in memory
        if self._backend is not None:
            try:
                loaded = self._backend.load_run(run_id)
                if loaded is None:
                    return None
                normalized = self._normalize_run(loaded)
                with self._lock:
                    self._runs[run_id] = normalized
                    if run_id not in self._order:
                        self._order.append(run_id)
                return dict(normalized)
            except Exception:
                pass
        return None

    def patch_run(self, run_id: str, fields: dict[str, Any]) -> dict[str, Any] | None:
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                return None
            for key, value in fields.items():
                run[key] = value
            snapshot = dict(run)
        self._save_backend(snapshot)
        return snapshot

    def update_status(
        self,
        run_id: str,
        new_status: str,
        **fields: Any,
    ) -> dict[str, Any] | None:
        if not self._state_machine.is_valid_status(new_status):
            raise ValueError(f"Invalid run status '{new_status}'.")

        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                return None

            current_status = str(run.get("status", RUN_STATUS_PENDING))
            self._state_machine.ensure_transition(current_status, new_status)

            now = _utc_now_iso()
            run["status"] = new_status

            if new_status in {RUN_STATUS_RUNNING, RUN_STATUS_REPLAYING}:
                run["started_at"] = run.get("started_at") or now
                run["finished_at"] = None
            if new_status in TERMINAL_RUN_STATUSES:
                run["finished_at"] = now

            for key, value in fields.items():
                run[key] = value

            snapshot = dict(run)

        self._save_backend(snapshot)
        return snapshot

    def list_runs(self, *, limit: int = 100) -> list[dict[str, Any]]:
        # Prefer backend if available (has full history)
        if self._backend is not None:
            try:
                rows = self._backend.list_runs(limit=limit)
                return [self._normalize_run(row) for row in rows]
            except Exception:
                pass
        return self.list_runs_page(limit=limit)

    def list_runs_page(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        safe_limit = max(1, min(int(limit), 500))
        safe_offset = max(0, int(offset))
        status_filter = status if status in RUN_STATUSES else None

        with self._lock:
            ordered = [dict(self._runs[rid]) for rid in reversed(self._order) if rid in self._runs]

        if status_filter is not None:
            ordered = [run for run in ordered if run.get("status") == status_filter]

        return ordered[safe_offset : safe_offset + safe_limit]

    def count_runs(self, *, status: str | None = None) -> int:
        status_filter = status if status in RUN_STATUSES else None
        with self._lock:
            runs = [self._runs[rid] for rid in self._order if rid in self._runs]
        if status_filter is None:
            return len(runs)
        return sum(1 for run in runs if run.get("status") == status_filter)

    def complete_run(self, run_id: str, result: dict[str, Any]) -> None:
        run = self.update_status(
            run_id,
            RUN_STATUS_COMPLETED,
            result=result,
            error=None,
        )
        if run is not None:
            self._persist(run_id)

    def fail_run(self, run_id: str, error: str) -> None:
        run = self.update_status(
            run_id,
            RUN_STATUS_FAILED,
            error=error,
            result=None,
        )
        if run is not None:
            self._persist(run_id)

    def cancel_run(self, run_id: str, reason: str = "Canceled by client") -> dict[str, Any] | None:
        snapshot = self.update_status(
            run_id,
            RUN_STATUS_CANCELED,
            error=reason,
            result=None,
        )
        if snapshot is None:
            return None
        self._persist(run_id)
        return snapshot

    def mark_waiting_for_human(
        self,
        run_id: str,
        *,
        current_step_id: str | None = None,
        checkpoint_head: str | None = None,
        approval_request: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        return self.update_status(
            run_id,
            "waiting_for_human",
            current_step_id=current_step_id,
            checkpoint_head=checkpoint_head,
            approval_request=approval_request or {},
        )

    def resume_run(
        self,
        run_id: str,
        *,
        resume_from_checkpoint_id: str | None = None,
    ) -> dict[str, Any] | None:
        return self.update_status(
            run_id,
            RUN_STATUS_RUNNING,
            resume_from_checkpoint_id=resume_from_checkpoint_id,
        )

    def approve_run(
        self,
        run_id: str,
        *,
        approver: str | None = None,
        notes: str | None = None,
        confirmed_capabilities: list[str] | None = None,
        resume_from_checkpoint_id: str | None = None,
    ) -> dict[str, Any] | None:
        run = self.get_run(run_id)
        if run is None:
            return None
        metadata = dict(run.get("metadata") or {})
        existing_confirmed = metadata.get("confirmed_capabilities")
        merged_confirmed: list[str] = []
        if isinstance(existing_confirmed, list):
            merged_confirmed.extend(
                item for item in existing_confirmed if isinstance(item, str)
            )
        if isinstance(confirmed_capabilities, list):
            for item in confirmed_capabilities:
                if isinstance(item, str) and item not in merged_confirmed:
                    merged_confirmed.append(item)
        metadata["confirmed_capabilities"] = merged_confirmed

        approval_request = dict(run.get("approval_request") or {})
        approval_request.update(
            {
                "status": "approved",
                "approver": approver,
                "notes": notes,
            }
        )

        return self.update_status(
            run_id,
            RUN_STATUS_RUNNING,
            metadata=metadata,
            approval_request=approval_request,
            resume_from_checkpoint_id=resume_from_checkpoint_id,
        )

    def deny_run(
        self,
        run_id: str,
        *,
        approver: str | None = None,
        notes: str | None = None,
        reason: str = "Denied by approver",
    ) -> dict[str, Any] | None:
        run = self.get_run(run_id)
        if run is None:
            return None
        approval_request = dict(run.get("approval_request") or {})
        approval_request.update(
            {
                "status": "denied",
                "approver": approver,
                "notes": notes,
            }
        )
        snapshot = self.update_status(
            run_id,
            RUN_STATUS_CANCELED,
            approval_request=approval_request,
            error=reason,
            result=None,
        )
        if snapshot is not None:
            self._persist(run_id)
        return snapshot

    def replay_run(
        self,
        run_id: str,
        *,
        skill_id: str,
        trace_id: str | None = None,
        source_run_id: str | None = None,
        source_checkpoint_id: str | None = None,
        checkpoint_head: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        replay_metadata = dict(metadata or {})
        replay_metadata["source_run_id"] = source_run_id
        replay_metadata["source_checkpoint_id"] = source_checkpoint_id
        replay_metadata["replay_mode"] = "checkpoint_replay"
        return self.create_run_record(
            run_id=run_id,
            skill_id=skill_id,
            trace_id=trace_id,
            status=RUN_STATUS_REPLAYING,
            checkpoint_head=checkpoint_head,
            metadata=replay_metadata,
        )

    def fork_run(
        self,
        run_id: str,
        *,
        skill_id: str,
        trace_id: str | None = None,
        source_run_id: str | None = None,
        source_checkpoint_id: str | None = None,
        checkpoint_head: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        fork_metadata = dict(metadata or {})
        fork_metadata["source_run_id"] = source_run_id
        fork_metadata["source_checkpoint_id"] = source_checkpoint_id
        fork_metadata["fork_mode"] = "checkpoint_fork"
        return self.create_run_record(
            run_id=run_id,
            skill_id=skill_id,
            trace_id=trace_id,
            status=RUN_STATUS_PENDING,
            checkpoint_head=checkpoint_head,
            metadata=fork_metadata,
        )

    # ── Internal ─────────────────────────────────────────────────────────

    def _evict(self) -> None:
        """Remove oldest runs when exceeding max_runs.  Caller holds lock."""
        while len(self._order) > self._max_runs:
            oldest = self._order.pop(0)
            self._runs.pop(oldest, None)

    def _normalize_run(self, run: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(run)
        status = str(normalized.get("status") or RUN_STATUS_RUNNING)
        if status not in RUN_STATUSES:
            status = RUN_STATUS_RUNNING
        normalized["status"] = status
        normalized.setdefault("thread_id", None)
        normalized.setdefault("session_id", None)
        normalized.setdefault("skill_version", None)
        normalized.setdefault("started_at", normalized.get("created_at"))
        normalized.setdefault("finished_at", None)
        normalized.setdefault("current_step_id", None)
        normalized.setdefault("checkpoint_head", None)
        normalized.setdefault("resume_from_checkpoint_id", None)
        normalized.setdefault("tenant_id", None)
        normalized.setdefault("environment", None)
        normalized.setdefault("policy_snapshot_id", None)
        normalized.setdefault("versions", {})
        normalized.setdefault("metadata", {})
        normalized.setdefault("result", None)
        normalized.setdefault("error", None)
        return normalized

    def _save_backend(self, run: dict[str, Any]) -> None:
        if self._backend is None:
            return
        try:
            self._backend.save_run(run)
        except Exception:
            # backend persistence is best-effort
            pass

    def _persist(self, run_id: str) -> None:
        if self._persist_path is None:
            return
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                return
            snapshot = dict(run)
        try:
            self._persist_path.parent.mkdir(parents=True, exist_ok=True)
            with self._persist_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(snapshot, ensure_ascii=False, default=str) + "\n")
        except Exception:
            pass  # persistence is best-effort


class RunStore(RunStoreV2):
    """Compatibility alias preserving existing imports while using v2 internals."""



def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

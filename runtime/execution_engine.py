from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import datetime, timezone
from uuid import uuid4
from typing import Any

from runtime.errors import (
    FinalOutputValidationError,
    GateExecutionError,
    InvalidExecutionOptionsError,
    SafetyConfirmationRequiredError,
    SafetyGateFailedError,
    SafetyTrustLevelError,
    StepExecutionError,
    StepTimeoutError,
)
from runtime.execution_state import (
    create_execution_state,
    emit_event,
    mark_finished,
    mark_started,
    record_step_result,
)
from runtime.execution_planner import validate_consumes_chain
from runtime.input_mapper import build_step_input
from runtime.models import (
    ExecutionContext,
    ExecutionRequest,
    SkillExecutionResult,
    StepResult,
    TraceStep,
)
from runtime.observability import elapsed_ms, log_event, reset_current_trace_id, set_current_trace_id
from runtime.otel_integration import start_span, record_exception
from runtime.output_mapper import apply_step_output
from runtime.scheduler import Scheduler, _NoopLock
from runtime.step_control import (
    StepSkipped,
    check_condition,
    RetryPolicy,
    ForeachConfig,
    WhileConfig,
    RouterConfig,
    ScatterConfig,
    invoke_with_retry,
    execute_foreach,
    execute_while,
    resolve_router,
    execute_scatter,
)

# Trust-level ranks used for safety enforcement.
_TRUST_LEVEL_RANK: dict[str, int] = {
    "sandbox": 0,
    "standard": 1,
    "elevated": 2,
    "privileged": 3,
}

# Default per-step timeout in seconds. Overridable in skill step config.
_DEFAULT_STEP_TIMEOUT_SECONDS = 60.0


def _build_auto_wire_mapping(
    capability,
    cognitive_types: dict[str, Any],
) -> dict[str, str] | None:
    """
    Build a synthetic output mapping from cognitive_hints.produces when the
    step has no explicit output_mapping.

    Resolution: for each field in produces, use the field's target override
    if present, otherwise the type's default_slot from cognitive_types.
    Returns None if no mapping can be derived.
    """
    hints = getattr(capability, "cognitive_hints", None)
    if not hints or not isinstance(hints, dict):
        return None
    produces = hints.get("produces")
    if not produces or not isinstance(produces, dict):
        return None

    types_defs = cognitive_types.get("types", {})
    mapping: dict[str, str] = {}
    for field_name, field_spec in produces.items():
        if not isinstance(field_spec, dict):
            continue
        target = field_spec.get("target")
        if isinstance(target, str) and target:
            mapping[field_name] = target
            continue
        type_name = field_spec.get("type")
        type_def = types_defs.get(type_name) if isinstance(type_name, str) else None
        if isinstance(type_def, dict):
            slot = type_def.get("default_slot")
            if isinstance(slot, str) and slot:
                mapping[field_name] = slot
    return mapping or None


class ExecutionEngine:
    """
    Core runtime engine responsible for executing a skill.

    Responsibilities:
    - load skill
    - build execution plan
    - resolve step inputs
    - execute capabilities or nested skills
    - apply step outputs
    - validate final outputs
    """

    def __init__(
        self,
        skill_loader,
        capability_loader,
        execution_planner,
        reference_resolver,
        capability_executor,
        nested_skill_runner,
        audit_recorder,
        scheduler=None,  # Nuevo parámetro opcional
        webhook_store=None,  # Optional WebhookStore for event delivery
    ) -> None:
        self.skill_loader = skill_loader
        self.capability_loader = capability_loader
        self.execution_planner = execution_planner
        self.reference_resolver = reference_resolver
        self.capability_executor = capability_executor
        self.nested_skill_runner = nested_skill_runner
        self.audit_recorder = audit_recorder
        self.scheduler = scheduler or Scheduler()
        self.webhook_store = webhook_store

    # ------------------------------------------------------------------
    # Safety enforcement
    # ------------------------------------------------------------------

    def _enforce_safety(
        self,
        capability,
        step,
        context: ExecutionContext,
        step_input: dict[str, Any],
    ) -> str | None:
        """
        Enforce safety policy declared on a capability.

        Returns None on success.  May return a reason string when the gate
        policy is 'degrade' (caller should skip the step).  Raises on
        'block' or 'require_human' policies.
        """
        safety: dict[str, Any] | None = getattr(capability, "safety", None)
        if not safety:
            return None

        # 1. Trust-level check
        required_trust = safety.get("trust_level")
        if isinstance(required_trust, str):
            required_rank = _TRUST_LEVEL_RANK.get(required_trust, 1)
            context_rank = _TRUST_LEVEL_RANK.get(
                context.options.trust_level, 1,
            )
            if context_rank < required_rank:
                raise SafetyTrustLevelError(
                    f"Capability '{capability.id}' requires trust_level "
                    f"'{required_trust}' (rank {required_rank}) but context "
                    f"provides '{context.options.trust_level}' "
                    f"(rank {context_rank}).",
                    capability_id=capability.id,
                    step_id=step.id,
                )

        # 2. requires_confirmation
        if safety.get("requires_confirmation") is True:
            confirmed = context.options.confirmed_capabilities
            if capability.id not in confirmed:
                raise SafetyConfirmationRequiredError(
                    f"Capability '{capability.id}' requires human "
                    f"confirmation before execution.",
                    capability_id=capability.id,
                    step_id=step.id,
                )

        # 3. mandatory_pre_gates
        degrade = self._run_gates(
            safety.get("mandatory_pre_gates"),
            capability,
            step,
            context,
            step_input,
            phase="pre",
        )
        if degrade is not None:
            return degrade

        return None

    @staticmethod
    def _resolve_deadline(
        options: ExecutionOptions,
        parent_context: ExecutionContext | None,
    ) -> float | None:
        """Propagate or create a monotonic deadline for the execution lineage."""
        if parent_context is not None and parent_context.deadline is not None:
            return parent_context.deadline
        if options.max_lineage_timeout_seconds is not None:
            return time.monotonic() + options.max_lineage_timeout_seconds
        return None

    def _run_gates(
        self,
        gates: list[dict[str, str]] | None,
        capability,
        step,
        context: ExecutionContext,
        step_input: dict[str, Any],
        phase: str,
    ) -> str | None:
        """
        Run a list of gate capabilities.

        Returns None if all gates pass.  Returns a reason string when a gate
        triggers the 'degrade' policy.  Raises on 'block' or 'require_human'.
        """
        if not gates:
            return None

        for gate in gates:
            gate_cap_id = gate.get("capability", "")
            on_fail = gate.get("on_fail", "block")

            try:
                gate_cap = self.capability_loader.get_capability(gate_cap_id)
                gate_result = self.capability_executor.execute(
                    gate_cap,
                    step_input,
                    trace_id=context.trace_id,
                )
                produced = gate_result[0] if isinstance(gate_result, tuple) else gate_result
            except Exception as exc:
                log_event(
                    "safety_gate.execution_error",
                    level="warning",
                    gate_capability=gate_cap_id,
                    phase=phase,
                    step_id=step.id,
                    error=str(exc),
                )
                raise GateExecutionError(
                    f"Safety gate '{gate_cap_id}' ({phase}) failed to execute: {exc}",
                    capability_id=getattr(capability, "id", None),
                    step_id=step.id,
                    cause=exc,
                ) from exc

            allowed = True
            reason = ""
            if isinstance(produced, dict):
                allowed = produced.get("allowed", True) is not False
                reason = produced.get("reason", "")

            if not allowed:
                if on_fail == "warn":
                    emit_event(
                        context.state,
                        "safety_gate_warning",
                        f"Safety gate '{gate_cap_id}' ({phase}) warned: {reason}",
                        step_id=step.id,
                    )
                    continue
                if on_fail == "degrade":
                    return (
                        f"Safety gate '{gate_cap_id}' ({phase}) "
                        f"triggered degrade: {reason}"
                    )
                if on_fail == "require_human":
                    raise SafetyConfirmationRequiredError(
                        f"Safety gate '{gate_cap_id}' ({phase}) "
                        f"requires human review: {reason}",
                        capability_id=capability.id,
                        step_id=step.id,
                    )
                # default: block
                raise SafetyGateFailedError(
                    f"Safety gate '{gate_cap_id}' ({phase}) "
                    f"blocked execution: {reason}",
                    capability_id=capability.id,
                    step_id=step.id,
                )
        return None

    def _run_post_gates(
        self,
        capability,
        step,
        context: ExecutionContext,
        produced: Any,
    ) -> None:
        """Run mandatory_post_gates after successful capability execution."""
        safety: dict[str, Any] | None = getattr(capability, "safety", None)
        if not safety:
            return
        post_gates = safety.get("mandatory_post_gates")
        if not post_gates:
            return
        # Post gates receive the produced output as their input.
        gate_input = produced if isinstance(produced, dict) else {"output": produced}
        self._run_gates(
            post_gates,
            capability,
            step,
            context,
            gate_input,
            phase="post",
        )

    def execute(
        self,
        request: ExecutionRequest,
        parent_context: ExecutionContext | None = None,
        trace_callback=None,
    ) -> SkillExecutionResult:
        """
        Execute a skill and return the final result.
        """
        start_time = time.perf_counter()
        skill = self.skill_loader.get_skill(request.skill_id)
        trace_id = request.trace_id or (parent_context.trace_id if parent_context else None) or str(uuid4())

        with start_span("skill.execute", attributes={
            "skill.id": skill.id,
            "skill.trace_id": trace_id,
            "skill.depth": (parent_context.depth + 1) if parent_context else 0,
        }) as _otel_span:
            return self._execute_inner(
                request, skill, trace_id, start_time, parent_context, trace_callback, _otel_span,
            )

    def _execute_inner(
        self,
        request: ExecutionRequest,
        skill,
        trace_id: str,
        start_time: float,
        parent_context: ExecutionContext | None,
        trace_callback,
        _otel_span,
    ) -> SkillExecutionResult:
        trace_token = set_current_trace_id(trace_id)
        state = None
        context = None
        execution_error: Exception | None = None

        try:
            state = create_execution_state(skill.id, request.inputs, trace_id=trace_id)

            context = ExecutionContext(
                state=state,
                options=request.options,
                depth=(parent_context.depth + 1) if parent_context else 0,
                parent_skill_id=parent_context.state.skill_id if parent_context else None,
                lineage=(
                    (*parent_context.lineage, skill.id)
                    if parent_context
                    else (skill.id,)
                ),
                trace_id=trace_id,
                channel=request.channel,
                deadline=self._resolve_deadline(request.options, parent_context),
            )

            mark_started(state)

            log_event(
                "skill.execute.start",
                trace_id=trace_id,
                skill_id=skill.id,
                depth=context.depth,
                lineage=list(context.lineage),
            )

            emit_event(
                state,
                "skill_start",
                f"Executing skill '{skill.id}'.",
            )

            if trace_callback:
                trace_callback(state.events[-1])

            plan = self.execution_planner.build_plan(skill)

            consumes_warnings = validate_consumes_chain(plan, self.capability_loader)
            for w in consumes_warnings:
                emit_event(state, "consumes_warning", w)

            # --- INTEGRACIÓN DEL SCHEDULER ---
            def step_executor(step, skill_id, context, trace_callback):
                return self._execute_step(step, skill_id, context, trace_callback)

            # Allow per-request max_workers override via ExecutionOptions
            opts_workers = getattr(context.options, "max_workers", None)
            if isinstance(opts_workers, int) and opts_workers > 0:
                self.scheduler.max_workers = opts_workers

            results = self.scheduler.schedule(plan, context, step_executor, trace_callback)
            for result in results:
                record_step_result(state, result)
                if result.status not in ("completed", "degraded", "skipped"):
                    if context.options.fail_fast:
                        mark_finished(state, "failed")
                        log_event(
                            "skill.execute.failed",
                            level="error",
                            trace_id=trace_id,
                            skill_id=skill.id,
                            failed_step_id=result.step_id,
                            duration_ms=elapsed_ms(start_time),
                            reason=result.error_message,
                        )
                        raise StepExecutionError(
                            f"Step '{result.step_id}' failed: {result.error_message}",
                            skill_id=skill.id,
                            step_id=result.step_id,
                        )

            self._validate_final_outputs(skill, state)

            mark_finished(state, "completed")

            emit_event(
                state,
                "skill_completed",
                f"Skill '{skill.id}' completed.",
            )

            if trace_callback:
                trace_callback(state.events[-1])

            log_event(
                "skill.execute.completed",
                trace_id=trace_id,
                skill_id=skill.id,
                status=state.status,
                steps_total=len(state.step_results),
                outputs=list(state.outputs.keys()),
                duration_ms=elapsed_ms(start_time),
            )

            self._emit_webhook("skill.completed", {
                "skill_id": skill.id,
                "status": state.status,
                "outputs": list(state.outputs.keys()),
                "duration_ms": elapsed_ms(start_time),
            }, trace_id=trace_id)

            return SkillExecutionResult(
                skill_id=skill.id,
                status=state.status,
                outputs=dict(state.outputs),
                state=state,
            )
        except Exception as e:
            execution_error = e
            record_exception(_otel_span, e)
            if state is not None and state.status != "completed":
                mark_finished(state, "failed")
            if state is not None:
                log_event(
                    "skill.execute.failed",
                    level="error",
                    trace_id=trace_id,
                    skill_id=skill.id,
                    depth=(context.depth if context is not None else 0),
                    duration_ms=elapsed_ms(start_time),
                    error_type=type(e).__name__,
                    error_message=str(e),
                )
                self._emit_webhook("skill.failed", {
                    "skill_id": skill.id,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                }, trace_id=trace_id)
            raise
        finally:
            if state is not None and context is not None:
                try:
                    self.audit_recorder.record_execution(
                        skill_id=skill.id,
                        state=state,
                        options=context.options,
                        channel=context.channel,
                        depth=context.depth,
                        parent_skill_id=context.parent_skill_id,
                        lineage=context.lineage,
                        error=execution_error,
                    )
                except InvalidExecutionOptionsError:
                    raise
                except Exception as audit_error:
                    log_event(
                        "audit.write.failed",
                        level="error",
                        trace_id=trace_id,
                        skill_id=skill.id,
                        error_type=type(audit_error).__name__,
                        error_message=str(audit_error),
                    )
            reset_current_trace_id(trace_token)

    def _execute_step(
        self,
        step,
        skill_id: str,
        context: ExecutionContext,
        trace_callback=None,
    ) -> StepResult:
        with start_span("step.execute", attributes={
            "step.id": step.id,
            "step.uses": step.uses,
            "skill.id": skill_id,
        }) as _step_span:
            return self._execute_step_inner(step, skill_id, context, trace_callback, _step_span)

    def _execute_step_inner(
        self,
        step,
        skill_id: str,
        context: ExecutionContext,
        trace_callback,
        _step_span,
    ) -> StepResult:
        state = context.state
        state_lock = getattr(context, "state_lock", _NoopLock())
        step_start = time.perf_counter()
        step_started_at = _utc_now()

        log_event(
            "step.execute.start",
            trace_id=context.trace_id,
            skill_id=skill_id,
            step_id=step.id,
            uses=step.uses,
        )

        # CognitiveState v1: track current step and updated_at
        with state_lock:
            state.current_step = step.id
            state.updated_at = _utc_now()

            emit_event(
                state,
                "step_start",
                f"Starting step '{step.id}'.",
                step_id=step.id,
            )

            if trace_callback:
                trace_callback(state.events[-1])

            step_input = build_step_input(
                step,
                state,
                self.reference_resolver,
            )

        try:
            # ── Condition gate (all step types) ──────────────────────────
            try:
                check_condition(step.config, state)
            except StepSkipped as skip:
                with state_lock:
                    emit_event(
                        state,
                        "step_skipped",
                        str(skip),
                        step_id=step.id,
                    )
                return StepResult(
                    step_id=step.id,
                    uses=step.uses,
                    status="skipped",
                    resolved_input=step_input,
                    started_at=step_started_at,
                    finished_at=_utc_now(),
                    latency_ms=elapsed_ms(step_start),
                )

            # ── Parse control-flow config ────────────────────────────────
            retry = RetryPolicy.from_config(step.config.get("retry"))
            foreach = ForeachConfig.from_config(step.config.get("foreach"))
            while_cfg = WhileConfig.from_config(step.config.get("while"))

            meta: dict | None = None
            attempts_count = None
            fallback_used = None
            conformance_profile = None
            required_profile = None
            _while_applied = False

            if step.uses.startswith("skill:"):
                # Nested skills support condition + retry (not foreach/while).
                def _invoke_skill():
                    return self.nested_skill_runner.execute(
                        step.uses,
                        step_input,
                        context,
                    ), None

                produced, meta = invoke_with_retry(_invoke_skill, retry)
            else:
                # ── Router: resolve capability dynamically ───────────
                router_cfg = RouterConfig.from_config(step.config.get("router"))
                scatter_cfg = ScatterConfig.from_config(step.config.get("scatter"))

                if router_cfg is not None:
                    resolved_cap_id, router_meta = resolve_router(router_cfg, state)
                    capability = self.capability_loader.get_capability(resolved_cap_id)
                else:
                    capability = self.capability_loader.get_capability(step.uses)
                    router_meta = None

                # --- Safety enforcement (pre-execution) ---
                degrade_reason = self._enforce_safety(
                    capability, step, context, step_input,
                )
                if degrade_reason is not None:
                    with state_lock:
                        emit_event(
                            state,
                            "step_degraded",
                            f"Step '{step.id}' degraded: {degrade_reason}",
                            step_id=step.id,
                        )
                    return StepResult(
                        step_id=step.id,
                        uses=step.uses,
                        status="degraded",
                        resolved_input=step_input,
                        produced_output=None,
                        error_message=degrade_reason,
                        started_at=step_started_at,
                        finished_at=_utc_now(),
                        latency_ms=elapsed_ms(step_start),
                    )

                step_timeout = self._resolve_step_timeout(step, context)

                # ── Single-invocation callable ───────────────────────
                def _invoke_once(extra_input=None, cap_override=None):
                    effective_cap = cap_override or capability
                    effective_input = dict(step_input)
                    if extra_input:
                        effective_input.update(extra_input)
                    cancel_event = threading.Event()
                    with ThreadPoolExecutor(max_workers=1) as pool:
                        future = pool.submit(
                            self.capability_executor.execute,
                            effective_cap,
                            effective_input,
                            trace_id=context.trace_id,
                            required_conformance_profile=context.options.required_conformance_profile,
                            trace_callback=trace_callback,
                            cancel_event=cancel_event,
                        )
                        try:
                            result = future.result(timeout=step_timeout)
                        except FuturesTimeoutError:
                            cancel_event.set()
                            future.cancel()
                            raise StepTimeoutError(
                                f"Step '{step.id}' exceeded timeout of {step_timeout}s.",
                                skill_id=skill_id,
                            )
                    if isinstance(result, tuple):
                        return result
                    return result, None

                # ── Dispatch control flow ────────────────────────────
                if scatter_cfg is not None:
                    # Scatter: parallel fan-out, mutually exclusive with
                    # foreach/while/router.
                    def _scatter_invoke(cap_id: str):
                        cap = self.capability_loader.get_capability(cap_id)
                        return _invoke_once(cap_override=cap)

                    produced, meta = execute_scatter(
                        scatter_cfg, _scatter_invoke, retry,
                    )
                elif foreach is not None:
                    produced, meta = execute_foreach(
                        foreach,
                        state,
                        lambda extra_vars: _invoke_once(extra_vars),
                        retry,
                    )
                elif while_cfg is not None:
                    auto_wire_w = self._resolve_auto_wire(step, capability)

                    def _while_apply(p):
                        with state_lock:
                            # Allow overwrite between iterations
                            for tgt in (auto_wire_w or step.output_mapping).values():
                                state.written_targets.discard(tgt)
                            apply_step_output(
                                step, p, state, mapping_override=auto_wire_w,
                            )

                    produced, meta = execute_while(
                        while_cfg,
                        state,
                        lambda: _invoke_once(),
                        _while_apply,
                        retry,
                    )
                    _while_applied = True
                else:
                    produced, meta = invoke_with_retry(
                        lambda: _invoke_once(), retry,
                    )

                # Merge router meta into step meta
                if router_meta is not None:
                    if meta is None:
                        meta = {}
                    meta.update(router_meta)

                # --- Safety enforcement (post-execution) ---
                self._run_post_gates(capability, step, context, produced)

                if isinstance(meta, dict):
                    attempts = meta.get("attempts")
                    if isinstance(attempts, list):
                        attempts_count = len(attempts)
                    fallback_raw = meta.get("fallback_used")
                    if isinstance(fallback_raw, bool):
                        fallback_used = fallback_raw
                    if isinstance(meta.get("conformance_profile"), str):
                        conformance_profile = meta.get("conformance_profile")
                    if isinstance(meta.get("required_conformance_profile"), str):
                        required_profile = meta.get("required_conformance_profile")

            with state_lock:
                # While loops already apply output each iteration
                if not _while_applied:
                    auto_wire = None
                    if not step.output_mapping and not step.uses.startswith("skill:"):
                        auto_wire = self._resolve_auto_wire(step, capability)
                    apply_step_output(
                        step,
                        produced,
                        state,
                        mapping_override=auto_wire,
                    )

                # emit completion event including produced output and metadata
                event_data: dict[str, Any] = {}
                if produced is not None:
                    event_data["produced_output"] = produced
                if meta:
                    event_data.update(meta)

                emit_event(
                    state,
                    "step_completed",
                    f"Step '{step.id}' completed.",
                    step_id=step.id,
                    data=event_data if event_data else None,
                )
                if trace_callback:
                    trace_callback(state.events[-1])

            log_event(
                "step.execute.completed",
                trace_id=context.trace_id,
                skill_id=skill_id,
                step_id=step.id,
                uses=step.uses,
                duration_ms=elapsed_ms(step_start),
                binding_id=(meta.get("binding_id") if meta else None),
                service_id=(meta.get("service_id") if meta else None),
            )

            # CognitiveState v1: enrich trace
            step_latency_ms = elapsed_ms(step_start)
            step_finished_at = _utc_now()
            reads = tuple(self._collect_reads(step.input_mapping))
            writes = tuple(step.output_mapping.values())

            with state_lock:
                state.trace.steps.append(TraceStep(
                    step_id=step.id,
                    capability_id=step.uses,
                    status="completed",
                    started_at=step_started_at,
                    ended_at=step_finished_at,
                    reads=reads,
                    writes=writes,
                    latency_ms=step_latency_ms,
                ))
                state.trace.metrics.step_count += 1
                state.trace.metrics.elapsed_ms += step_latency_ms
                if isinstance(meta, dict):
                    state.trace.metrics.llm_calls += meta.get("llm_calls", 0)
                    state.trace.metrics.tool_calls += meta.get("tool_calls", 0)
                    state.trace.metrics.tokens_in += meta.get("tokens_in", 0)
                    state.trace.metrics.tokens_out += meta.get("tokens_out", 0)
                state.current_step = None
                state.updated_at = step_finished_at

            return StepResult(
                step_id=step.id,
                uses=step.uses,
                status="completed",
                resolved_input=step_input,
                produced_output=produced,
                binding_id=(meta.get("binding_id") if meta else None),
                service_id=(meta.get("service_id") if meta else None),
                attempts_count=attempts_count,
                fallback_used=fallback_used,
                conformance_profile=conformance_profile,
                required_conformance_profile=required_profile,
                started_at=step_started_at,
                finished_at=_utc_now(),
                # CognitiveState v1: data lineage
                reads=tuple(self._collect_reads(step.input_mapping)),
                writes=tuple(step.output_mapping.values()),
                latency_ms=step_latency_ms,
            )

        except (SafetyTrustLevelError, SafetyGateFailedError, SafetyConfirmationRequiredError, GateExecutionError):
            raise
        except Exception as e:
            record_exception(_step_span, e)
            fail_latency_ms = elapsed_ms(step_start)
            fail_finished_at = _utc_now()
            log_event(
                "step.execute.failed",
                level="error",
                trace_id=context.trace_id,
                skill_id=skill_id,
                step_id=step.id,
                uses=step.uses,
                duration_ms=fail_latency_ms,
                error_type=type(e).__name__,
                error_message=str(e),
            )
            with state_lock:
                emit_event(
                    state,
                    "step_failed",
                    f"Step '{step.id}' failed.",
                    step_id=step.id,
                    data={"error": str(e)},
                )
                if trace_callback:
                    trace_callback(state.events[-1])

                # CognitiveState v1: trace failed step
                state.trace.steps.append(TraceStep(
                    step_id=step.id,
                    capability_id=step.uses,
                    status="failed",
                    started_at=step_started_at,
                    ended_at=fail_finished_at,
                    reads=tuple(self._collect_reads(step.input_mapping)),
                    writes=(),
                    latency_ms=fail_latency_ms,
                ))
                state.trace.metrics.step_count += 1
                state.trace.metrics.elapsed_ms += fail_latency_ms
                state.current_step = None
                state.updated_at = fail_finished_at

            return StepResult(
                step_id=step.id,
                uses=step.uses,
                status="failed",
                resolved_input={},
                produced_output=None,
                error_message=str(e),
                started_at=step_started_at,
                finished_at=fail_finished_at,
                latency_ms=fail_latency_ms,
            )

    def _resolve_auto_wire(self, step, capability) -> dict[str, str] | None:
        """Build auto-wire mapping when step has no explicit output_mapping."""
        if step.output_mapping:
            return None
        ct = getattr(self.capability_loader, "get_cognitive_types", None)
        if ct is not None:
            return _build_auto_wire_mapping(capability, ct())
        return None

    def _emit_webhook(self, event_type: str, data: dict[str, Any], *, trace_id: str | None = None) -> None:
        """Fire-and-forget webhook delivery if a store is configured."""
        store = self.webhook_store
        if store is None:
            return
        try:
            from runtime.webhook import deliver_event
            deliver_event(store, event_type, data, trace_id=trace_id)
        except Exception:
            pass  # never fail the execution because of webhook delivery

    @staticmethod
    def _resolve_step_timeout(step, context) -> float:
        """Resolve timeout for a step: step config > options > default."""
        step_val = step.config.get("timeout_seconds") if hasattr(step, "config") else None
        if isinstance(step_val, (int, float)) and step_val > 0:
            return float(step_val)
        opts_val = getattr(context.options, "default_step_timeout_seconds", None)
        if isinstance(opts_val, (int, float)) and opts_val > 0:
            return float(opts_val)
        return _DEFAULT_STEP_TIMEOUT_SECONDS

    @staticmethod
    def _collect_reads(input_mapping: dict[str, Any]) -> list[str]:
        """Extract namespace references from an input mapping (for data lineage)."""
        refs: list[str] = []
        _extract_refs(input_mapping, refs)
        return refs

    def _validate_final_outputs(self, skill, state) -> None:
        """
        Ensure all required skill outputs have been produced.
        """
        for name, spec in skill.outputs.items():
            if spec.required and name not in state.outputs:
                raise FinalOutputValidationError(
                    f"Required output '{name}' not produced.",
                    skill_id=skill.id,
                )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# Known runtime namespaces for reference extraction (data lineage).
_REF_NAMESPACES = frozenset({
    "inputs", "vars", "outputs", "frame", "working", "output", "extensions",
})


def _extract_refs(value: Any, refs: list[str]) -> None:
    """Recursively collect namespace references from a mapping value."""
    if isinstance(value, str) and "." in value:
        ns = value.split(".", 1)[0]
        if ns in _REF_NAMESPACES:
            refs.append(value)
    elif isinstance(value, dict):
        for v in value.values():
            _extract_refs(v, refs)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _extract_refs(item, refs)
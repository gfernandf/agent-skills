from __future__ import annotations

import time
from datetime import datetime, timezone
from uuid import uuid4
from typing import Any

from runtime.errors import (
    FinalOutputValidationError,
    InvalidExecutionOptionsError,
    StepExecutionError,
)
from runtime.execution_state import (
    create_execution_state,
    emit_event,
    mark_finished,
    mark_started,
    record_step_result,
)
from runtime.input_mapper import build_step_input
from runtime.models import (
    ExecutionContext,
    ExecutionRequest,
    SkillExecutionResult,
    StepResult,
)
from runtime.observability import elapsed_ms, log_event, reset_current_trace_id, set_current_trace_id
from runtime.output_mapper import apply_step_output
from runtime.scheduler import Scheduler, _NoopLock


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
    ) -> None:
        self.skill_loader = skill_loader
        self.capability_loader = capability_loader
        self.execution_planner = execution_planner
        self.reference_resolver = reference_resolver
        self.capability_executor = capability_executor
        self.nested_skill_runner = nested_skill_runner
        self.audit_recorder = audit_recorder
        self.scheduler = scheduler or Scheduler()

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

            # --- INTEGRACIÓN DEL SCHEDULER ---
            def step_executor(step, skill_id, context, trace_callback):
                return self._execute_step(step, skill_id, context, trace_callback)

            results = self.scheduler.schedule(plan, context, step_executor, trace_callback)
            for result in results:
                record_step_result(state, result)
                if result.status != "completed":
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

            return SkillExecutionResult(
                skill_id=skill.id,
                status=state.status,
                outputs=dict(state.outputs),
                state=state,
            )
        except Exception as e:
            execution_error = e
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

        with state_lock:
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
            meta: dict | None = None
            attempts_count = None
            fallback_used = None
            conformance_profile = None
            required_profile = None
            if step.uses.startswith("skill:"):
                produced = self.nested_skill_runner.execute(
                    step.uses,
                    step_input,
                    context,
                )
            else:
                capability = self.capability_loader.get_capability(step.uses)

                result = self.capability_executor.execute(
                    capability,
                    step_input,
                    trace_id=context.trace_id,
                    required_conformance_profile=context.options.required_conformance_profile,
                    trace_callback=trace_callback,
                )

                if isinstance(result, tuple):
                    produced, meta = result
                else:
                    produced, meta = result, None

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
                apply_step_output(
                    step,
                    produced,
                    state,
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
            )

        except Exception as e:
            log_event(
                "step.execute.failed",
                level="error",
                trace_id=context.trace_id,
                skill_id=skill_id,
                step_id=step.id,
                uses=step.uses,
                duration_ms=elapsed_ms(step_start),
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

            return StepResult(
                step_id=step.id,
                uses=step.uses,
                status="failed",
                resolved_input={},
                produced_output=None,
                error_message=str(e),
                started_at=step_started_at,
                finished_at=_utc_now(),
            )

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
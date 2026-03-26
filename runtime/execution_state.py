from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from runtime.models import ExecutionState, FrameState, RuntimeEvent, StepResult


def create_execution_state(
    skill_id: str,
    inputs: dict[str, Any],
    trace_id: str | None = None,
    *,
    frame: FrameState | None = None,
    skill_version: str | None = None,
    parent_run_id: str | None = None,
) -> ExecutionState:
    """
    Create the initial mutable execution state for a skill run.

    CognitiveState v1: initialises cognitive structures alongside legacy fields.
    All new fields have safe defaults so existing callers are unaffected.
    """
    now = _utc_now()
    return ExecutionState(
        skill_id=skill_id,
        inputs=dict(inputs),
        vars={},
        outputs={},
        step_results={},
        written_targets=set(),
        events=[],
        started_at=now,
        finished_at=None,
        status="pending",
        trace_id=trace_id,
        # CognitiveState v1
        frame=frame or FrameState(),
        skill_version=skill_version,
        parent_run_id=parent_run_id,
        updated_at=now,
    )


def add_event(state: ExecutionState, event: RuntimeEvent) -> None:
    """
    Append a runtime event to the execution state.
    """
    state.events.append(event)


def emit_event(
    state: ExecutionState,
    event_type: str,
    message: str,
    *,
    step_id: str | None = None,
    data: dict[str, Any] | None = None,
) -> RuntimeEvent:
    """
    Convenience helper to create and append a runtime event in one call.
    """
    event = RuntimeEvent(
        type=event_type,
        message=message,
        timestamp=_utc_now(),
        step_id=step_id,
        trace_id=state.trace_id,
        data=dict(data or {}),
    )
    add_event(state, event)
    return event


def set_status(state: ExecutionState, status: str) -> None:
    """
    Update the execution status.

    Expected statuses are runtime-defined strings such as:
    pending, running, completed, failed.
    """
    state.status = status


def mark_started(state: ExecutionState) -> None:
    """
    Mark the execution as started/running.
    """
    state.started_at = state.started_at or _utc_now()
    state.status = "running"


def mark_finished(state: ExecutionState, status: str) -> None:
    """
    Mark the execution as finished with the provided final status.
    """
    state.finished_at = _utc_now()
    state.status = status


def record_step_result(state: ExecutionState, result: StepResult) -> None:
    """
    Record or replace the result of a step execution by step id.
    """
    state.step_results[result.step_id] = result


def get_step_result(state: ExecutionState, step_id: str) -> StepResult | None:
    """
    Return the recorded step result for the given step id, if any.
    """
    return state.step_results.get(step_id)


def mark_target_written(state: ExecutionState, target: str) -> None:
    """
    Mark a runtime target (vars.* or outputs.*) as already written.
    """
    state.written_targets.add(target)


def has_written_target(state: ExecutionState, target: str) -> bool:
    """
    Return whether a runtime target has already been written.
    """
    return target in state.written_targets


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)

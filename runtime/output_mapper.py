from __future__ import annotations

from typing import Any

from runtime.errors import OutputMappingError
from runtime.execution_state import has_written_target, mark_target_written
from runtime.models import ExecutionState, StepSpec


def apply_step_output(
    step: StepSpec,
    step_output: dict[str, Any],
    state: ExecutionState,
) -> None:
    """
    Apply a step-produced output payload into runtime targets.

    The declarative mapping is:

        step.output_mapping:
            <produced_field> -> <target_ref>

    Supported target namespaces (v1):
    - vars.<field>
    - outputs.<field>

    Not allowed:
    - inputs.<field>
    - duplicate writes to the same target during one execution
    """
    if not isinstance(step_output, dict):
        raise OutputMappingError(
            f"Step '{step.id}' produced a non-mapping output.",
            skill_id=state.skill_id,
            step_id=step.id,
        )

    for produced_field, target_ref in step.output_mapping.items():
        if produced_field not in step_output:
            raise OutputMappingError(
                f"Step '{step.id}' did not produce required output field '{produced_field}'.",
                skill_id=state.skill_id,
                step_id=step.id,
            )

        _write_target(
            target_ref=target_ref,
            value=step_output[produced_field],
            state=state,
            step_id=step.id,
        )


def _write_target(
    target_ref: str,
    value: Any,
    state: ExecutionState,
    step_id: str,
) -> None:
    namespace, field = _parse_target_ref(target_ref, state, step_id)

    if has_written_target(state, target_ref):
        raise OutputMappingError(
            f"Target '{target_ref}' has already been written.",
            skill_id=state.skill_id,
            step_id=step_id,
        )

    if namespace == "vars":
        state.vars[field] = value
    elif namespace == "outputs":
        state.outputs[field] = value
    else:
        # Defensive branch: _parse_target_ref already validates namespaces.
        raise OutputMappingError(
            f"Unsupported output target namespace '{namespace}'.",
            skill_id=state.skill_id,
            step_id=step_id,
        )

    mark_target_written(state, target_ref)


def _parse_target_ref(
    target_ref: str,
    state: ExecutionState,
    step_id: str,
) -> tuple[str, str]:
    if not isinstance(target_ref, str) or not target_ref:
        raise OutputMappingError(
            "Output target reference must be a non-empty string.",
            skill_id=state.skill_id,
            step_id=step_id,
        )

    if "." not in target_ref:
        raise OutputMappingError(
            f"Invalid output target reference '{target_ref}'. Expected namespace.field form.",
            skill_id=state.skill_id,
            step_id=step_id,
        )

    namespace, field = target_ref.split(".", 1)

    if not field:
        raise OutputMappingError(
            f"Invalid output target reference '{target_ref}'. Missing target field.",
            skill_id=state.skill_id,
            step_id=step_id,
        )

    if namespace == "inputs":
        raise OutputMappingError(
            f"Step '{step_id}' cannot write to input target '{target_ref}'.",
            skill_id=state.skill_id,
            step_id=step_id,
        )

    if namespace not in {"vars", "outputs"}:
        raise OutputMappingError(
            f"Invalid output target namespace in '{target_ref}'.",
            skill_id=state.skill_id,
            step_id=step_id,
        )

    return namespace, field
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
        try:
            produced_value = _resolve_produced_path(step_output, produced_field, state=state)
        except OutputMappingError:
            raise
        except Exception as e:
            raise OutputMappingError(
                f"Step '{step.id}' did not produce required output field '{produced_field}'.",
                skill_id=state.skill_id,
                step_id=step.id,
                cause=e,
            ) from e

        _write_target(
            target_ref=target_ref,
            value=produced_value,
            state=state,
            step_id=step.id,
        )


def _resolve_produced_path(
    step_output: dict[str, Any],
    produced_field: str,
    *,
    state: ExecutionState,
) -> Any:
    """
    Resolve a produced output reference from a step output payload.

    Supports direct keys and nested dotted paths, e.g.:
    - summary
    - output.summary
    - output.items.0.id
    """
    if not isinstance(produced_field, str) or not produced_field:
        raise OutputMappingError("Produced field reference must be a non-empty string.")

    if produced_field.startswith("vars."):
        key = produced_field.split(".", 1)[1]
        if key not in state.vars:
            raise OutputMappingError(
                f"Produced field '{produced_field}' not found in step output."
            )
        return state.vars[key]

    if produced_field.startswith("inputs."):
        key = produced_field.split(".", 1)[1]
        if key not in state.inputs:
            raise OutputMappingError(
                f"Produced field '{produced_field}' not found in step output."
            )
        return state.inputs[key]

    if produced_field.startswith("outputs."):
        key = produced_field.split(".", 1)[1]
        if key not in state.outputs:
            raise OutputMappingError(
                f"Produced field '{produced_field}' not found in step output."
            )
        return state.outputs[key]

    if "." not in produced_field:
        if produced_field not in step_output:
            raise OutputMappingError(
                f"Produced field '{produced_field}' not found in step output."
            )
        return step_output[produced_field]

    current: Any = step_output
    for part in produced_field.split("."):
        if not part:
            raise OutputMappingError(
                f"Invalid produced field reference '{produced_field}'."
            )

        if isinstance(current, dict):
            if part not in current:
                raise OutputMappingError(
                    f"Produced field '{produced_field}' not found in step output."
                )
            current = current[part]
            continue

        if isinstance(current, list):
            if not part.isdigit():
                raise OutputMappingError(
                    f"Invalid list index '{part}' in produced field '{produced_field}'."
                )
            idx = int(part)
            if idx < 0 or idx >= len(current):
                raise OutputMappingError(
                    f"Out-of-range list index '{part}' in produced field '{produced_field}'."
                )
            current = current[idx]
            continue

        raise OutputMappingError(
            f"Produced field '{produced_field}' cannot be resolved from non-container value."
        )

    return current


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
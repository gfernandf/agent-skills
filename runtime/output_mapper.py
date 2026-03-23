from __future__ import annotations

from typing import Any

from runtime.errors import OutputMappingError
from runtime.execution_state import has_written_target, mark_target_written
from runtime.models import ExecutionState, StepSpec


# Namespaces writable by step output mappings.
_WRITABLE_NAMESPACES = frozenset({"vars", "outputs", "working", "output", "extensions"})

# Namespaces that are never writable.
_READ_ONLY_NAMESPACES = frozenset({"inputs", "frame", "trace"})

# Valid merge strategies for step config.
_MERGE_STRATEGIES = frozenset({"overwrite", "append", "deep_merge", "replace"})


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

    Supported target namespaces:
    - vars.<field>       (legacy)
    - outputs.<field>    (legacy)
    - working.<path>     (CognitiveState v1)
    - output.<path>      (CognitiveState v1)
    - extensions.<path>  (CognitiveState v1)

    Not allowed:
    - inputs.<field>
    - frame.<field>
    - trace.<field>

    Merge strategies (via step.config["merge_strategy"]):
    - overwrite   (default): error on duplicate write
    - append      : extend existing list with new items
    - deep_merge  : recursive dict merge
    - replace     : overwrite without duplicate error
    """
    if not isinstance(step_output, dict):
        raise OutputMappingError(
            f"Step '{step.id}' produced a non-mapping output.",
            skill_id=state.skill_id,
            step_id=step.id,
        )

    merge_strategy = step.config.get("merge_strategy", "overwrite")
    if merge_strategy not in _MERGE_STRATEGIES:
        raise OutputMappingError(
            f"Step '{step.id}' has invalid merge_strategy '{merge_strategy}'.",
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
            merge_strategy=merge_strategy,
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
    merge_strategy: str = "overwrite",
) -> None:
    namespace, rest = _parse_target_ref(target_ref, state, step_id)

    # ── Duplicate-write guard ────────────────────────
    if merge_strategy == "overwrite":
        if has_written_target(state, target_ref):
            raise OutputMappingError(
                f"Target '{target_ref}' has already been written.",
                skill_id=state.skill_id,
                step_id=step_id,
            )
    elif merge_strategy in ("append", "deep_merge"):
        pass  # allow repeated writes — that's the point
    elif merge_strategy == "replace":
        pass  # intentional overwrite, no duplicate check

    # ── Legacy flat namespaces ───────────────────────
    if namespace == "vars":
        _apply_to_flat(state.vars, rest, value, target_ref, state, step_id, merge_strategy)
    elif namespace == "outputs":
        _apply_to_flat(state.outputs, rest, value, target_ref, state, step_id, merge_strategy)

    # ── Cognitive namespaces (nested path) ───────────
    elif namespace in ("working", "output", "extensions"):
        root = getattr(state, namespace)
        _apply_to_nested(root, rest, value, target_ref, state, step_id, merge_strategy)
    else:
        raise OutputMappingError(
            f"Unsupported output target namespace '{namespace}'.",
            skill_id=state.skill_id,
            step_id=step_id,
        )

    mark_target_written(state, target_ref)


def _apply_to_flat(
    container: dict[str, Any],
    field: str,
    value: Any,
    target_ref: str,
    state: ExecutionState,
    step_id: str,
    merge_strategy: str,
) -> None:
    """Write to a flat dict (vars / outputs) with merge strategy."""
    if merge_strategy == "append":
        existing = container.get(field, [])
        if not isinstance(existing, list):
            raise OutputMappingError(
                f"append requires existing target '{target_ref}' to be a list, got {type(existing).__name__}.",
                skill_id=state.skill_id, step_id=step_id,
            )
        if not isinstance(value, list):
            raise OutputMappingError(
                f"append requires produced value for '{target_ref}' to be a list, got {type(value).__name__}.",
                skill_id=state.skill_id, step_id=step_id,
            )
        existing.extend(value)
        container[field] = existing

    elif merge_strategy == "deep_merge":
        existing = container.get(field, {})
        if not isinstance(existing, dict) or not isinstance(value, dict):
            raise OutputMappingError(
                f"deep_merge requires both target and value for '{target_ref}' to be dicts.",
                skill_id=state.skill_id, step_id=step_id,
            )
        _deep_merge(existing, value)
        container[field] = existing

    else:
        # overwrite / replace
        container[field] = value


def _apply_to_nested(
    root: Any,
    path: str,
    value: Any,
    target_ref: str,
    state: ExecutionState,
    step_id: str,
    merge_strategy: str,
) -> None:
    """
    Write to a nested path within a cognitive structure.

    Traversal: dataclass attrs → dict keys → auto-create intermediate dicts.
    """
    segments = path.split(".")
    current = root

    # Walk to the parent of the final segment, creating intermediate dicts as needed.
    for segment in segments[:-1]:
        # dataclass attribute
        if hasattr(type(current), "__dataclass_fields__") and segment in type(current).__dataclass_fields__:
            current = getattr(current, segment)
            continue

        # dict — auto-create nested dicts
        if isinstance(current, dict):
            if segment not in current:
                current[segment] = {}
            current = current[segment]
            continue

        raise OutputMappingError(
            f"Cannot traverse path '{path}' for target '{target_ref}': "
            f"segment '{segment}' is not navigable on {type(current).__name__}.",
            skill_id=state.skill_id,
            step_id=step_id,
        )

    # ── Write final segment ──────────────────────────
    final = segments[-1]

    # Target is a dataclass attr whose value is a dict (e.g. working.artifacts)
    if hasattr(type(current), "__dataclass_fields__") and final in type(current).__dataclass_fields__:
        container = getattr(current, final)
        # If the attr is itself a dict, merge strategies apply to the whole dict
        if isinstance(container, dict) and isinstance(value, dict):
            if merge_strategy == "deep_merge":
                _deep_merge(container, value)
            elif merge_strategy == "append":
                raise OutputMappingError(
                    f"append not applicable: target '{target_ref}' is a dict, not a list.",
                    skill_id=state.skill_id, step_id=step_id,
                )
            else:
                # overwrite / replace — set each key
                setattr(current, final, value)
        elif isinstance(container, list) and merge_strategy == "append":
            if not isinstance(value, list):
                raise OutputMappingError(
                    f"append requires produced value for '{target_ref}' to be a list.",
                    skill_id=state.skill_id, step_id=step_id,
                )
            container.extend(value)
        else:
            setattr(current, final, value)
        return

    # Target is a dict key
    if isinstance(current, dict):
        if merge_strategy == "append":
            existing = current.get(final, [])
            if not isinstance(existing, list):
                raise OutputMappingError(
                    f"append requires existing target '{target_ref}' to be a list.",
                    skill_id=state.skill_id, step_id=step_id,
                )
            if not isinstance(value, list):
                raise OutputMappingError(
                    f"append requires produced value for '{target_ref}' to be a list.",
                    skill_id=state.skill_id, step_id=step_id,
                )
            existing.extend(value)
            current[final] = existing

        elif merge_strategy == "deep_merge":
            existing = current.get(final, {})
            if not isinstance(existing, dict) or not isinstance(value, dict):
                raise OutputMappingError(
                    f"deep_merge requires both target and value for '{target_ref}' to be dicts.",
                    skill_id=state.skill_id, step_id=step_id,
                )
            _deep_merge(existing, value)
            current[final] = existing

        else:
            # overwrite / replace
            current[final] = value
        return

    raise OutputMappingError(
        f"Cannot write final segment '{final}' for target '{target_ref}' on {type(current).__name__}.",
        skill_id=state.skill_id,
        step_id=step_id,
    )


def _deep_merge(base: dict, overlay: dict) -> None:
    """Recursively merge overlay into base. Overlay keys win for non-dict values."""
    for key, val in overlay.items():
        if key in base and isinstance(base[key], dict) and isinstance(val, dict):
            _deep_merge(base[key], val)
        else:
            base[key] = val


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

    if namespace in _READ_ONLY_NAMESPACES:
        raise OutputMappingError(
            f"Step '{step_id}' cannot write to read-only namespace '{namespace}' in target '{target_ref}'.",
            skill_id=state.skill_id,
            step_id=step_id,
        )

    if namespace not in _WRITABLE_NAMESPACES:
        raise OutputMappingError(
            f"Invalid output target namespace in '{target_ref}'.",
            skill_id=state.skill_id,
            step_id=step_id,
        )

    return namespace, field
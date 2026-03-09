from __future__ import annotations

from typing import Any

from runtime.errors import InputMappingError, ReferenceResolutionError
from runtime.models import ExecutionState, StepSpec
from runtime.reference_resolver import ReferenceResolver


def build_step_input(
    step: StepSpec,
    state: ExecutionState,
    reference_resolver: ReferenceResolver,
) -> dict[str, Any]:
    """
    Resolve the declarative input mapping of a step into a concrete runtime payload.

    The engine passes the resulting payload to either:
    - a capability executor
    - a nested skill runner

    Resolution rules:
    - scalar literals are preserved
    - strings in the supported reference namespaces are resolved
    - nested dict/list structures are resolved recursively
    """
    try:
        return _resolve_value(step.input_mapping, state, reference_resolver, step.id)
    except InputMappingError:
        raise
    except ReferenceResolutionError as e:
        raise InputMappingError(
            f"Failed to resolve input mapping for step '{step.id}'.",
            skill_id=state.skill_id,
            step_id=step.id,
            cause=e,
        ) from e
    except Exception as e:
        raise InputMappingError(
            f"Failed to build step input for step '{step.id}'.",
            skill_id=state.skill_id,
            step_id=step.id,
            cause=e,
        ) from e


def _resolve_value(
    value: Any,
    state: ExecutionState,
    reference_resolver: ReferenceResolver,
    step_id: str,
) -> Any:
    """
    Recursively resolve a declarative value.

    Supported recursive structures:
    - dict
    - list

    Tuples are converted to lists only if they appear as already-loaded YAML-like
    data structures, but in practice YAML sources should yield dict/list/scalars.
    """
    if isinstance(value, dict):
        resolved: dict[str, Any] = {}
        for key, nested_value in value.items():
            if not isinstance(key, str) or not key:
                raise InputMappingError(
                    "Step input mapping contains an invalid key.",
                    skill_id=state.skill_id,
                    step_id=step_id,
                )
            resolved[key] = _resolve_value(
                nested_value,
                state,
                reference_resolver,
                step_id,
            )
        return resolved

    if isinstance(value, list):
        return [
            _resolve_value(item, state, reference_resolver, step_id)
            for item in value
        ]

    return reference_resolver.resolve(value, state)
from __future__ import annotations

from typing import Any

from runtime.errors import ReferenceResolutionError
from runtime.models import ExecutionState


class ReferenceResolver:
    """
    Resolves declarative references used inside step input mappings.

    Supported namespaces (v1):

        inputs.<field>
        vars.<field>
        outputs.<field>

    If a value is not a string or does not contain a dot namespace prefix,
    it is treated as a literal and returned as-is.
    """

    def resolve(self, value: Any, state: ExecutionState) -> Any:
        """
        Resolve a single mapping value.

        Literal values pass through unchanged.
        Namespaced references are resolved against ExecutionState.
        """
        if not isinstance(value, str):
            return value

        if "." not in value:
            return value

        namespace, field = value.split(".", 1)

        if namespace == "inputs":
            return self._resolve_inputs(field, state)

        if namespace == "vars":
            return self._resolve_vars(field, state)

        if namespace == "outputs":
            return self._resolve_outputs(field, state)

        raise ReferenceResolutionError(
            f"Unknown reference namespace '{namespace}'."
        )

    def resolve_mapping(self, mapping: dict[str, Any], state: ExecutionState) -> dict[str, Any]:
        """
        Resolve all values inside a mapping structure.

        This is used primarily by the InputMapper before invoking a step.
        """
        resolved: dict[str, Any] = {}

        for key, value in mapping.items():
            resolved[key] = self.resolve(value, state)

        return resolved

    def _resolve_inputs(self, field: str, state: ExecutionState) -> Any:
        if field not in state.inputs:
            raise ReferenceResolutionError(
                f"Input '{field}' not found in execution inputs.",
                skill_id=state.skill_id,
            )
        return state.inputs[field]

    def _resolve_vars(self, field: str, state: ExecutionState) -> Any:
        if field not in state.vars:
            raise ReferenceResolutionError(
                f"Variable '{field}' not found in execution vars.",
                skill_id=state.skill_id,
            )
        return state.vars[field]

    def _resolve_outputs(self, field: str, state: ExecutionState) -> Any:
        if field not in state.outputs:
            raise ReferenceResolutionError(
                f"Output '{field}' not found in execution outputs.",
                skill_id=state.skill_id,
            )
        return state.outputs[field]
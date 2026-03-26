from __future__ import annotations

from typing import Any

from runtime.errors import ReferenceResolutionError
from runtime.models import ExecutionState


# Namespaces that return None on missing keys instead of raising.
_PERMISSIVE_NAMESPACES = frozenset({"inputs", "frame", "extensions"})

# Namespaces that require the value to exist (raise on missing).
_STRICT_NAMESPACES = frozenset({"vars", "outputs", "working"})

# Read-only cognitive namespaces resolved via path traversal.
_COGNITIVE_NAMESPACES = frozenset({"frame", "working", "output", "extensions"})

# All known runtime namespaces — anything else is treated as a literal.
_ALL_NAMESPACES = frozenset({"inputs", "vars", "outputs"}) | _COGNITIVE_NAMESPACES


class ReferenceResolver:
    """
    Resolves declarative references used inside step input mappings.

    Supported namespaces:

        Legacy (v0):
            inputs.<field>   → state.inputs[field]       (None if missing)
            vars.<field>     → state.vars[field]          (error if missing)
            outputs.<field>  → state.outputs[field]       (error if missing)

        CognitiveState v1:
            frame.<path>      → state.frame.<path>        (None if missing)
            working.<path>    → state.working.<path>      (error if missing)
            output.<path>     → state.output.<path>       (None if missing)
            extensions.<path> → state.extensions[<path>]  (None if missing)

    Path traversal supports dataclass attributes, dict keys, and list indices.
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

        namespace, rest = value.split(".", 1)

        if namespace not in _ALL_NAMESPACES:
            # Not a known namespace — treat as literal (e.g. natural language).
            return value

        # ── Legacy flat namespaces ──────────────────────
        if namespace == "inputs":
            return self._resolve_flat(state.inputs, rest, permissive=True, state=state)

        if namespace == "vars":
            return self._resolve_flat(state.vars, rest, permissive=False, state=state)

        if namespace == "outputs":
            return self._resolve_flat(
                state.outputs, rest, permissive=False, state=state
            )

        # ── Cognitive namespaces (path traversal) ───────
        root = getattr(state, namespace)
        permissive = namespace in _PERMISSIVE_NAMESPACES or namespace == "output"
        return self._walk_path(
            root, rest, full_ref=value, permissive=permissive, state=state
        )

    def resolve_mapping(
        self, mapping: dict[str, Any], state: ExecutionState
    ) -> dict[str, Any]:
        """
        Resolve all values inside a mapping structure.

        This is used primarily by the InputMapper before invoking a step.
        """
        resolved: dict[str, Any] = {}

        for key, value in mapping.items():
            resolved[key] = self.resolve(value, state)

        return resolved

    # ── Internal helpers ────────────────────────────────

    def _resolve_flat(
        self,
        container: dict[str, Any],
        field: str,
        *,
        permissive: bool,
        state: ExecutionState,
    ) -> Any:
        """Resolve a single key from a flat dict (legacy namespaces)."""
        if field not in container:
            if permissive:
                return None
            raise ReferenceResolutionError(
                f"Key '{field}' not found.",
                skill_id=state.skill_id,
            )
        return container[field]

    def _walk_path(
        self,
        root: Any,
        path: str,
        *,
        full_ref: str,
        permissive: bool,
        state: ExecutionState,
    ) -> Any:
        """
        Walk a dotted path against a root value.

        Traversal rules:
        - dataclass attribute → getattr
        - dict key            → dict[key]
        - list index (digit)  → list[int(segment)]
        """
        current = root
        for segment in path.split("."):
            if current is None:
                if permissive:
                    return None
                raise ReferenceResolutionError(
                    f"Cannot resolve '{full_ref}': path segment '{segment}' hit None.",
                    skill_id=state.skill_id,
                )

            # dataclass attribute
            if (
                hasattr(type(current), "__dataclass_fields__")
                and segment in type(current).__dataclass_fields__
            ):
                current = getattr(current, segment)
                continue

            # dict key
            if isinstance(current, dict):
                if segment in current:
                    current = current[segment]
                    continue
                if permissive:
                    return None
                raise ReferenceResolutionError(
                    f"Cannot resolve '{full_ref}': key '{segment}' not found.",
                    skill_id=state.skill_id,
                )

            # list index
            if isinstance(current, (list, tuple)) and segment.isdigit():
                idx = int(segment)
                if 0 <= idx < len(current):
                    current = current[idx]
                    continue
                if permissive:
                    return None
                raise ReferenceResolutionError(
                    f"Cannot resolve '{full_ref}': index {idx} out of range.",
                    skill_id=state.skill_id,
                )

            # Nothing matched
            if permissive:
                return None
            raise ReferenceResolutionError(
                f"Cannot resolve '{full_ref}': cannot traverse '{segment}' on {type(current).__name__}.",
                skill_id=state.skill_id,
            )

        return current

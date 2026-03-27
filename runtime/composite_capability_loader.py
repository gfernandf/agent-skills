from __future__ import annotations

from typing import Sequence

from runtime.capability_loader import CapabilityLoader, YamlCapabilityLoader
from runtime.errors import (
    CapabilityNotFoundError,
    InvalidCapabilitySpecError,
    suggest_similar,
)
from runtime.models import CapabilitySpec, FieldSpec


class CompositeCapabilityLoader:
    """
    Chains multiple capability loaders with priority ordering and ``extends``
    resolution.

    Typical wiring::

        CompositeCapabilityLoader([
            YamlCapabilityLoader(local_caps_root),   # highest priority
            YamlCapabilityLoader(registry_root),      # shared registry
        ])

    Resolution rules:

    1. The **first** loader that provides a capability id wins (local > registry).
    2. If a loaded ``CapabilitySpec`` declares ``extends: <base_id>``, the base
       is resolved through the full chain and the contracts are merged:
       - Base inputs and outputs are inherited.
       - The extension may **add** new fields or override optional base fields.
       - The extension **cannot** make a base-required field optional.
    3. ``extends`` chains are resolved recursively (A extends B extends C) with a
       depth limit to prevent cycles.
    """

    _MAX_EXTENDS_DEPTH = 5

    def __init__(self, loaders: Sequence[CapabilityLoader]) -> None:
        if not loaders:
            raise ValueError("CompositeCapabilityLoader requires at least one loader.")
        self._loaders = list(loaders)

    # ── public API ────────────────────────────────────────────

    def get_capability(self, capability_id: str) -> CapabilitySpec:
        spec = self._raw_get(capability_id)
        if spec.extends:
            return self._resolve_extends(spec, depth=0)
        return spec

    def get_all_capabilities(self) -> dict[str, CapabilitySpec]:
        """De-duplicated union of all capabilities across loaders (priority order)."""
        seen: set[str] = set()
        result: dict[str, CapabilitySpec] = {}
        for loader in self._loaders:
            if isinstance(loader, YamlCapabilityLoader):
                raw_caps = loader.get_all_capabilities()
                for cap_id, cap in raw_caps.items():
                    if cap_id not in seen:
                        seen.add(cap_id)
                        if cap.extends:
                            try:
                                cap = self._resolve_extends(cap, depth=0)
                            except Exception:
                                pass  # skip unresolvable at listing time
                        result[cap_id] = cap
        return result

    def get_cognitive_types(self) -> dict:
        """Delegate to the first loader that has cognitive types."""
        for loader in self._loaders:
            if isinstance(loader, YamlCapabilityLoader):
                ct = loader.get_cognitive_types()
                if ct:
                    return ct
        return {}

    # ── internal ──────────────────────────────────────────────

    def _raw_get(self, capability_id: str) -> CapabilitySpec:
        last_exc: Exception | None = None
        all_ids: list[str] = []
        for loader in self._loaders:
            try:
                return loader.get_capability(capability_id)
            except CapabilityNotFoundError as exc:
                last_exc = exc
                if isinstance(loader, YamlCapabilityLoader):
                    if loader._capability_index is not None:
                        all_ids.extend(loader._capability_index.keys())
                continue

        msg = f"Capability '{capability_id}' not found in any registered source."
        similar = suggest_similar(capability_id, all_ids)
        if similar:
            msg += f" Did you mean: {', '.join(similar)}?"
        raise CapabilityNotFoundError(
            msg, capability_id=capability_id, cause=last_exc
        ) from last_exc

    def _resolve_extends(
        self, spec: CapabilitySpec, depth: int
    ) -> CapabilitySpec:
        if depth >= self._MAX_EXTENDS_DEPTH:
            raise InvalidCapabilitySpecError(
                f"Capability '{spec.id}' exceeds maximum extends depth "
                f"({self._MAX_EXTENDS_DEPTH}). Possible cycle in extends chain.",
                capability_id=spec.id,
            )

        base = self._raw_get(spec.extends)  # type: ignore[arg-type]
        # If the base itself extends, resolve recursively first.
        if base.extends:
            base = self._resolve_extends(base, depth + 1)

        merged_inputs = self._merge_fields(
            base.inputs, spec.inputs, "inputs", spec.id, base.id
        )
        merged_outputs = self._merge_fields(
            base.outputs, spec.outputs, "outputs", spec.id, base.id
        )

        # Properties: base as default, extension overrides.
        merged_properties = {**base.properties, **spec.properties}

        # Cognitive hints: extension wins entirely if provided, else base.
        merged_cognitive = spec.cognitive_hints if spec.cognitive_hints else base.cognitive_hints

        # Safety: extension wins entirely if provided, else base.
        merged_safety = spec.safety if spec.safety else base.safety

        return CapabilitySpec(
            id=spec.id,
            version=spec.version,
            description=spec.description,
            inputs=merged_inputs,
            outputs=merged_outputs,
            metadata=spec.metadata,
            properties=merged_properties,
            requires=spec.requires or base.requires,
            deprecated=spec.deprecated,
            replacement=spec.replacement,
            aliases=spec.aliases,
            extends=spec.extends,
            source_file=spec.source_file,
            cognitive_hints=merged_cognitive,
            safety=merged_safety,
        )

    @staticmethod
    def _merge_fields(
        base_fields: dict[str, FieldSpec],
        ext_fields: dict[str, FieldSpec],
        section: str,
        ext_id: str,
        base_id: str,
    ) -> dict[str, FieldSpec]:
        """Merge base and extension fields.

        Rules:
        - All base fields are inherited.
        - Extension may add new fields.
        - Extension may override an optional base field.
        - Extension **cannot** make a base-required field optional.
        """
        merged = dict(base_fields)

        for name, ext_field in ext_fields.items():
            base_field = merged.get(name)
            if base_field is not None and base_field.required and not ext_field.required:
                raise InvalidCapabilitySpecError(
                    f"Capability '{ext_id}' extends '{base_id}' but tries to make "
                    f"required {section} field '{name}' optional. "
                    f"Extensions cannot weaken required base fields.",
                    capability_id=ext_id,
                )
            merged[name] = ext_field

        return merged

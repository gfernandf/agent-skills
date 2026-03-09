from __future__ import annotations

from runtime.active_binding_map import ActiveBindingMap
from runtime.binding_models import ResolvedBinding
from runtime.binding_registry import BindingRegistry, BindingRegistryError
from runtime.errors import RuntimeErrorBase


class BindingResolutionError(RuntimeErrorBase):
    """Raised when no valid binding can be resolved for a capability."""


class BindingResolver:
    """
    Resolve the effective binding for a capability in the current host instance.

    Resolution policy (v1):
    1. If a local active binding exists for the capability, use it.
       - It may point to an official non-default binding
       - It may point to a local binding
    2. Otherwise, use the official default binding for the capability.
    3. If neither exists, raise BindingResolutionError
    """

    def __init__(
        self,
        binding_registry: BindingRegistry,
        active_binding_map: ActiveBindingMap,
    ) -> None:
        self.binding_registry = binding_registry
        self.active_binding_map = active_binding_map

    def resolve(self, capability_id: str) -> ResolvedBinding:
        if not isinstance(capability_id, str) or not capability_id:
            raise BindingResolutionError("Capability id must be a non-empty string.")

        active_binding_id = self.active_binding_map.get_active_binding_id(capability_id)
        if active_binding_id is not None:
            binding = self._get_binding_or_raise(
                binding_id=active_binding_id,
                capability_id=capability_id,
                selection_source="local_selection",
            )
            self._validate_binding_matches_capability(
                binding.id,
                binding.capability_id,
                capability_id,
                selection_source="local_selection",
            )
            return ResolvedBinding(
                capability_id=capability_id,
                binding_id=binding.id,
                service_id=binding.service_id,
                operation_id=binding.operation_id,
                protocol=binding.protocol,
                binding_source=binding.source,
                selection_source="local_selection",
            )

        default_binding_id = self.binding_registry.get_official_default_binding_id(capability_id)
        if default_binding_id is not None:
            binding = self._get_binding_or_raise(
                binding_id=default_binding_id,
                capability_id=capability_id,
                selection_source="official_default",
            )
            self._validate_binding_matches_capability(
                binding.id,
                binding.capability_id,
                capability_id,
                selection_source="official_default",
            )

            if binding.source != "official":
                raise BindingResolutionError(
                    f"Official default binding '{binding.id}' for capability '{capability_id}' "
                    f"is not official (source='{binding.source}').",
                    capability_id=capability_id,
                )

            return ResolvedBinding(
                capability_id=capability_id,
                binding_id=binding.id,
                service_id=binding.service_id,
                operation_id=binding.operation_id,
                protocol=binding.protocol,
                binding_source=binding.source,
                selection_source="official_default",
            )

        raise BindingResolutionError(
            f"No binding could be resolved for capability '{capability_id}'.",
            capability_id=capability_id,
        )

    def _get_binding_or_raise(
        self,
        *,
        binding_id: str,
        capability_id: str,
        selection_source: str,
    ):
        try:
            return self.binding_registry.get_binding(binding_id)
        except BindingRegistryError as e:
            raise BindingResolutionError(
                f"Resolved {selection_source} binding '{binding_id}' for capability "
                f"'{capability_id}' does not exist.",
                capability_id=capability_id,
                cause=e,
            ) from e

    def _validate_binding_matches_capability(
        self,
        binding_id: str,
        binding_capability_id: str,
        requested_capability_id: str,
        *,
        selection_source: str,
    ) -> None:
        if binding_capability_id != requested_capability_id:
            raise BindingResolutionError(
                f"Resolved {selection_source} binding '{binding_id}' targets capability "
                f"'{binding_capability_id}', not '{requested_capability_id}'.",
                capability_id=requested_capability_id,
            )
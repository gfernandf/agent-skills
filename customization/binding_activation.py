from __future__ import annotations

from pathlib import Path

from customization.binding_state_store import BindingStateStore
from customization.override_intent_loader import OverrideIntentLoader
from customization.quality_gate import QualityGate
from customization.service_descriptor_loader import ServiceDescriptorLoader
from runtime.binding_models import BindingSpec, OverrideIntent, ServiceDescriptor
from runtime.binding_registry import BindingRegistry, BindingRegistryError
from runtime.capability_loader import CapabilityLoader
from runtime.errors import RuntimeErrorBase


class BindingActivationError(RuntimeErrorBase):
    """Raised when local override activation cannot be completed."""


class BindingActivationService:
    """
    Resolve local override intent into an operational active binding map.

    Inputs:
    - .agent-skills/overrides.yaml
    - .agent-skills/services.yaml
    - official/local/candidate bindings from BindingRegistry
    - official capability definitions from CapabilityLoader

    Output:
    - .agent-skills/active_bindings.json
    """

    def __init__(
        self,
        repo_root: Path,
        host_root: Path,
        binding_registry: BindingRegistry,
        capability_loader: CapabilityLoader,
        service_loader: ServiceDescriptorLoader,
        override_loader: OverrideIntentLoader,
        state_store: BindingStateStore,
        quality_gate: QualityGate,
    ) -> None:
        self.repo_root = repo_root
        self.host_root = host_root
        self.binding_registry = binding_registry
        self.capability_loader = capability_loader
        self.service_loader = service_loader
        self.override_loader = override_loader
        self.state_store = state_store
        self.quality_gate = quality_gate

    def activate_all(self) -> dict[str, str]:
        """
        Apply all declared overrides and persist the resulting active binding map.

        Existing active bindings are preserved unless replaced by a newly resolved
        override during this activation pass.
        """
        active = self.state_store.load_active_bindings()
        overrides = self.override_loader.load()

        # Force local services loading early so configuration problems are surfaced
        # during activation, not later at execution time.
        self.service_loader.load()

        for intent in overrides:
            for capability_id in intent.capabilities:
                binding_id = self._resolve_intent_for_capability(
                    capability_id=capability_id,
                    intent=intent,
                )
                if binding_id is not None:
                    active[capability_id] = binding_id

        self.state_store.save_active_bindings(active)
        return active

    def activate_capability(self, capability_id: str) -> str:
        """
        Activate a single capability based on the first matching override intent.

        Raises if:
        - no applicable override exists
        - the override cannot be resolved
        """
        if not isinstance(capability_id, str) or not capability_id:
            raise BindingActivationError("Capability id must be a non-empty string.")

        # Force local services loading for early validation
        self.service_loader.load()

        overrides = self.override_loader.load()
        matching = [intent for intent in overrides if capability_id in intent.capabilities]

        if not matching:
            raise BindingActivationError(
                f"No override intent found for capability '{capability_id}'.",
                capability_id=capability_id,
            )

        binding_id = self._resolve_intent_for_capability(
            capability_id=capability_id,
            intent=matching[0],
        )
        if binding_id is None:
            raise BindingActivationError(
                f"Capability '{capability_id}' could not be activated.",
                capability_id=capability_id,
            )

        active = self.state_store.load_active_bindings()
        active[capability_id] = binding_id
        self.state_store.save_active_bindings(active)

        return binding_id

    def _resolve_intent_for_capability(
        self,
        *,
        capability_id: str,
        intent: OverrideIntent,
    ) -> str | None:
        capability = self._load_capability(capability_id)

        if intent.binding_id is not None:
            return self._resolve_binding_override(
                capability_id=capability_id,
                binding_id=intent.binding_id,
                source_file=intent.source_file,
            )

        if intent.service_id is not None:
            return self._resolve_service_override(
                capability_id=capability_id,
                service_id=intent.service_id,
                mode=intent.mode,
                source_file=intent.source_file,
            )

        raise BindingActivationError(
            f"Override intent for capability '{capability_id}' is invalid: "
            f"neither binding nor service was provided.",
            capability_id=capability_id,
        )

    def _resolve_binding_override(
        self,
        *,
        capability_id: str,
        binding_id: str,
        source_file: str | None,
    ) -> str:
        capability = self._load_capability(capability_id)

        try:
            binding = self.binding_registry.get_binding(binding_id)
        except BindingRegistryError as e:
            raise BindingActivationError(
                f"Override references unknown binding '{binding_id}' for capability '{capability_id}'.",
                capability_id=capability_id,
                cause=e,
            ) from e

        if binding.capability_id != capability_id:
            raise BindingActivationError(
                f"Binding '{binding_id}' targets capability '{binding.capability_id}', "
                f"not '{capability_id}'.",
                capability_id=capability_id,
            )

        service = self._load_service(binding.service_id)

        issues = self.quality_gate.validate_binding_for_capability(
            binding=binding,
            capability=capability,
            service=service,
        )
        if issues:
            raise BindingActivationError(
                f"Binding '{binding_id}' failed quality gate for capability '{capability_id}': "
                f"{'; '.join(issues)}",
                capability_id=capability_id,
            )

        return binding.id

    def _resolve_service_override(
        self,
        *,
        capability_id: str,
        service_id: str,
        mode: str,
        source_file: str | None,
    ) -> str | None:
        capability = self._load_capability(capability_id)
        service = self._load_service(service_id)

        candidates = self._find_bindings_for_capability_and_service(
            capability_id=capability_id,
            service_id=service_id,
        )

        valid_candidates: list[BindingSpec] = []
        for binding in candidates:
            issues = self.quality_gate.validate_binding_for_capability(
                binding=binding,
                capability=capability,
                service=service,
            )
            if not issues:
                valid_candidates.append(binding)

        if valid_candidates:
            # v1 policy: choose the first deterministic candidate after registry ordering.
            return valid_candidates[0].id

        if mode == "prefer":
            return None

        raise BindingActivationError(
            f"No valid binding found for capability '{capability_id}' using service '{service_id}'.",
            capability_id=capability_id,
        )

    def _find_bindings_for_capability_and_service(
        self,
        *,
        capability_id: str,
        service_id: str,
    ) -> list[BindingSpec]:
        bindings = self.binding_registry.get_bindings_for_capability(capability_id)

        filtered = [b for b in bindings if b.service_id == service_id]

        def sort_key(binding: BindingSpec) -> tuple[int, str]:
            source_rank = {
                "local": 0,
                "official": 1,
                "candidate": 2,
            }.get(binding.source, 99)
            return (source_rank, binding.id)

        return sorted(filtered, key=sort_key)

    def _load_capability(self, capability_id: str):
        try:
            return self.capability_loader.get_capability(capability_id)
        except Exception as e:
            raise BindingActivationError(
                f"Capability '{capability_id}' could not be loaded during activation.",
                capability_id=capability_id,
                cause=e,
            ) from e

    def _load_service(self, service_id: str) -> ServiceDescriptor:
        try:
            return self.binding_registry.get_service(service_id)
        except BindingRegistryError as e:
            raise BindingActivationError(
                f"Service '{service_id}' could not be resolved during activation.",
                cause=e,
            ) from e
from __future__ import annotations

import os

from runtime.active_binding_map import ActiveBindingMap
from runtime.binding_models import ResolvedBinding
from runtime.binding_registry import BindingRegistry, BindingRegistryError
from runtime.errors import RuntimeErrorBase

# Environment variable → service-id substring mapping.
# When the env var is present and non-empty the resolver prefers official
# bindings whose service_id contains the associated substring.
_ENV_SERVICE_PREFERENCES: list[tuple[str, str]] = [
    ("OPENAI_API_KEY", "openai"),
]


class BindingResolutionError(RuntimeErrorBase):
    """Raised when no valid binding can be resolved for a capability."""


class BindingResolver:
    """
    Resolve the effective binding for a capability in the current host instance.

    Resolution policy (v2 — environment-aware):
    1. If a local active binding exists for the capability, use it.
    2. Auto-detect available credentials and prefer the matching binding.
       - When OPENAI_API_KEY is set → prefer official OpenAI bindings.
       - When no recognised key is set → prefer official pythoncall bindings.
    3. Otherwise, use the official default binding for the capability.
    4. If none of the above resolves, raise BindingResolutionError.
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

        # --- 1. Explicit local override (highest priority) ---
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

        # --- 2. Environment-preferred binding ---
        env_binding_id = self._resolve_environment_preferred(capability_id)
        if env_binding_id is not None:
            binding = self._get_binding_or_raise(
                binding_id=env_binding_id,
                capability_id=capability_id,
                selection_source="environment_preferred",
            )
            self._validate_binding_matches_capability(
                binding.id,
                binding.capability_id,
                capability_id,
                selection_source="environment_preferred",
            )
            return ResolvedBinding(
                capability_id=capability_id,
                binding_id=binding.id,
                service_id=binding.service_id,
                operation_id=binding.operation_id,
                protocol=binding.protocol,
                binding_source=binding.source,
                selection_source="environment_preferred",
            )

        # --- 3. Official default (fallback policy) ---
        default_binding_id = self.binding_registry.get_official_default_binding_id(
            capability_id
        )
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

    # ------------------------------------------------------------------
    # Environment-aware binding preference
    # ------------------------------------------------------------------

    def _resolve_environment_preferred(self, capability_id: str) -> str | None:
        """
        Select an official binding based on available environment credentials.

        Heuristic (v1):
        - Scan ``_ENV_SERVICE_PREFERENCES`` for set env vars.
        - If a matching env var is found, pick the first official binding whose
          ``service_id`` contains the associated substring.
        - If *no* recognised credential is present, prefer an official
          ``pythoncall`` binding so that no external call is attempted.
        - Return ``None`` when the heuristic cannot improve on the official
          default (e.g. capability has a single binding).
        """
        bindings = self.binding_registry.get_bindings_for_capability(capability_id)
        official = [b for b in bindings if b.source == "official"]

        if len(official) <= 1:
            return None

        # Check recognised credentials in priority order.
        for env_var, service_substr in _ENV_SERVICE_PREFERENCES:
            if os.environ.get(env_var):
                preferred = [
                    b for b in official if service_substr in b.service_id.lower()
                ]
                if preferred:
                    return preferred[0].id

        # No recognised credential → prefer local pythoncall to avoid
        # wasted HTTP calls against services that will reject us.
        pythoncall = [b for b in official if b.protocol == "pythoncall"]
        if pythoncall:
            return pythoncall[0].id

        return None

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

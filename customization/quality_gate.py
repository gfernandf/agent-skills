from __future__ import annotations

from runtime.binding_models import BindingSpec, ServiceDescriptor
from runtime.models import CapabilitySpec


class QualityGate:
    """
    Minimal compatibility validator for capability <-> binding <-> service.

    v1 goal:
    - catch obvious incompatibilities early
    - keep validation simple, deterministic, and explainable
    - return issues instead of throwing, so activation logic can decide policy
    """

    def validate_binding_for_capability(
        self,
        binding: BindingSpec,
        capability: CapabilitySpec,
        service: ServiceDescriptor,
    ) -> list[str]:
        issues: list[str] = []

        if binding.capability_id != capability.id:
            issues.append(
                f"Binding '{binding.id}' targets capability '{binding.capability_id}', "
                f"but activation requested '{capability.id}'."
            )

        if binding.service_id != service.id:
            issues.append(
                f"Binding '{binding.id}' targets service '{binding.service_id}', "
                f"but activation is validating against service '{service.id}'."
            )

        if binding.protocol != service.kind:
            issues.append(
                f"Binding '{binding.id}' protocol '{binding.protocol}' does not match "
                f"service '{service.id}' kind '{service.kind}'."
            )

        issues.extend(
            self._validate_service_shape(service)
        )

        issues.extend(
            self._validate_required_outputs(binding, capability)
        )

        issues.extend(
            self._validate_conformance_profile(binding)
        )

        return issues

    def _validate_service_shape(self, service: ServiceDescriptor) -> list[str]:
        issues: list[str] = []

        if service.kind == "openapi":
            if service.spec_ref is None and service.base_url is None:
                issues.append(
                    f"Service '{service.id}' of kind 'openapi' must define at least "
                    f"one of 'spec_ref' or 'base_url'."
                )
            if service.server is not None:
                issues.append(
                    f"Service '{service.id}' of kind 'openapi' must not define 'server'."
                )
            if service.module is not None:
                issues.append(
                    f"Service '{service.id}' of kind 'openapi' must not define 'module'."
                )

        elif service.kind == "openrpc":
            if service.spec_ref is None and service.base_url is None:
                issues.append(
                    f"Service '{service.id}' of kind 'openrpc' must define at least "
                    f"one of 'spec_ref' or 'base_url'."
                )
            if service.server is not None:
                issues.append(
                    f"Service '{service.id}' of kind 'openrpc' must not define 'server'."
                )
            if service.module is not None:
                issues.append(
                    f"Service '{service.id}' of kind 'openrpc' must not define 'module'."
                )

        elif service.kind == "mcp":
            if service.server is None:
                issues.append(
                    f"Service '{service.id}' of kind 'mcp' must define 'server'."
                )
            if service.spec_ref is not None:
                issues.append(
                    f"Service '{service.id}' of kind 'mcp' must not define 'spec_ref'."
                )
            if service.base_url is not None:
                issues.append(
                    f"Service '{service.id}' of kind 'mcp' must not define 'base_url'."
                )
            if service.module is not None:
                issues.append(
                    f"Service '{service.id}' of kind 'mcp' must not define 'module'."
                )

        elif service.kind == "pythoncall":
            if service.module is None:
                issues.append(
                    f"Service '{service.id}' of kind 'pythoncall' must define 'module'."
                )
            if service.spec_ref is not None:
                issues.append(
                    f"Service '{service.id}' of kind 'pythoncall' must not define 'spec_ref'."
                )
            if service.base_url is not None:
                issues.append(
                    f"Service '{service.id}' of kind 'pythoncall' must not define 'base_url'."
                )
            if service.server is not None:
                issues.append(
                    f"Service '{service.id}' of kind 'pythoncall' must not define 'server'."
                )

        else:
            issues.append(
                f"Service '{service.id}' has unsupported kind '{service.kind}'."
            )

        return issues

    def _validate_required_outputs(
        self,
        binding: BindingSpec,
        capability: CapabilitySpec,
    ) -> list[str]:
        issues: list[str] = []

        for output_name, output_spec in capability.outputs.items():
            if output_spec.required and output_name not in binding.response_mapping:
                issues.append(
                    f"Binding '{binding.id}' does not map required capability output "
                    f"'{output_name}'."
                )

        return issues

    def _validate_conformance_profile(self, binding: BindingSpec) -> list[str]:
        issues: list[str] = []
        allowed = {"strict", "standard", "experimental"}

        profile = binding.metadata.get("conformance_profile") if isinstance(binding.metadata, dict) else None
        if profile is None:
            return issues

        if not isinstance(profile, str) or not profile:
            issues.append(
                f"Binding '{binding.id}' metadata.conformance_profile must be a non-empty string if present."
            )
            return issues

        if profile not in allowed:
            issues.append(
                f"Binding '{binding.id}' metadata.conformance_profile '{profile}' is invalid. Allowed: {', '.join(sorted(allowed))}."
            )

        return issues
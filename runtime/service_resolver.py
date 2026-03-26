from __future__ import annotations

from runtime.binding_models import ServiceDescriptor
from runtime.binding_registry import BindingRegistry, BindingRegistryError
from runtime.errors import RuntimeErrorBase


class ServiceResolutionError(RuntimeErrorBase):
    """Raised when a concrete service cannot be resolved for binding execution."""


class ServiceResolver:
    """
    Resolve a service descriptor from the consolidated binding registry.

    This indirection keeps BindingExecutor simple and gives us a dedicated place
    to enforce service-level validation/policies later without changing the
    execution pipeline.
    """

    def __init__(self, binding_registry: BindingRegistry) -> None:
        self.binding_registry = binding_registry

    def resolve(self, service_id: str) -> ServiceDescriptor:
        if not isinstance(service_id, str) or not service_id:
            raise ServiceResolutionError("Service id must be a non-empty string.")

        try:
            service = self.binding_registry.get_service(service_id)
        except BindingRegistryError as e:
            raise ServiceResolutionError(
                f"Service '{service_id}' could not be resolved.",
                cause=e,
            ) from e

        self._validate_service(service)

        return service

    def _validate_service(self, service: ServiceDescriptor) -> None:
        """
        Enforce runtime-level minimum validity for a service descriptor.

        The registry already performs structural loading validation, but this
        method gives the runtime a final defensive check before invocation.
        """
        if service.kind not in {"openapi", "mcp", "openrpc", "pythoncall"}:
            raise ServiceResolutionError(
                f"Service '{service.id}' has unsupported kind '{service.kind}'."
            )

        if service.kind in {"openapi", "openrpc"}:
            if service.spec_ref is None and service.base_url is None:
                raise ServiceResolutionError(
                    f"Service '{service.id}' must define at least one of "
                    f"'spec_ref' or 'base_url' for kind '{service.kind}'."
                )

        elif service.kind == "mcp":
            if service.server is None:
                raise ServiceResolutionError(
                    f"Service '{service.id}' must define 'server' for kind 'mcp'."
                )

        elif service.kind == "pythoncall":
            if service.module is None:
                raise ServiceResolutionError(
                    f"Service '{service.id}' must define 'module' for kind 'pythoncall'."
                )

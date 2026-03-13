from __future__ import annotations

from typing import Any

from runtime.binding_models import InvocationRequest, InvocationResponse
from runtime.binding_registry import BindingRegistry
from runtime.binding_resolver import BindingResolver
from runtime.errors import RuntimeErrorBase
from runtime.request_builder import RequestBuilder
from runtime.response_mapper import ResponseMapper
from runtime.service_resolver import ServiceResolver
from runtime.protocol_router import ProtocolRouter


class BindingExecutionError(RuntimeErrorBase):
    """Raised when a binding invocation fails."""


class BindingExecutor:
    """
    Execute a capability through the binding system.

    Pipeline implemented here:

        capability
            ↓
        binding resolution
            ↓
        request construction
            ↓
        protocol routing
            ↓
        service invocation
            ↓
        response mapping
            ↓
        capability output
    """

    def __init__(
        self,
        binding_registry: BindingRegistry,
        binding_resolver: BindingResolver,
        service_resolver: ServiceResolver,
        request_builder: RequestBuilder,
        protocol_router: ProtocolRouter,
        response_mapper: ResponseMapper,
    ) -> None:
        self.binding_registry = binding_registry
        self.binding_resolver = binding_resolver
        self.service_resolver = service_resolver
        self.request_builder = request_builder
        self.protocol_router = protocol_router
        self.response_mapper = response_mapper

    def execute(self, capability, step_input: dict, trace_callback=None) -> dict | tuple[dict, dict]:
        """
        Execute a capability using the resolved binding.

        Returns either a plain output mapping or a tuple `(outputs, metadata)`.
        Metadata contains binding/service identifiers useful for tracing.
        """

        capability_id = capability.id

        resolved = self.binding_resolver.resolve(capability_id)
        chain = self._build_fallback_chain(
            capability_id=capability_id,
            primary_binding_id=resolved.binding_id,
        )

        attempts: list[dict[str, Any]] = []
        last_error: Exception | None = None

        for index, binding_id in enumerate(chain):
            conformance_profile = "standard"
            try:
                binding = self.binding_registry.get_binding(binding_id)
                service = self.service_resolver.resolve(binding.service_id)
                conformance_profile = self._resolve_conformance_profile(binding.metadata)

                payload = self.request_builder.build(
                    binding=binding,
                    step_input=step_input,
                )

                invocation = InvocationRequest(
                    protocol=binding.protocol,
                    service=service,
                    binding=binding,
                    operation_id=binding.operation_id,
                    payload=payload,
                    context_metadata={
                        "capability_id": capability_id,
                        "binding_id": binding.id,
                        "service_id": service.id,
                    },
                )

                response: InvocationResponse = self.protocol_router.invoke(invocation)

                mapped_output = self.response_mapper.map(
                    binding=binding,
                    invocation_response=response,
                )

                attempts.append(
                    {
                        "binding_id": binding.id,
                        "service_id": service.id,
                        "status": "success",
                        "conformance_profile": conformance_profile,
                    }
                )

                return mapped_output, {
                    "binding_id": binding.id,
                    "service_id": service.id,
                    "conformance_profile": conformance_profile,
                    "fallback_used": index > 0,
                    "fallback_chain": list(chain),
                    "attempts": attempts,
                }

            except Exception as e:
                last_error = e
                attempts.append(
                    {
                        "binding_id": binding_id,
                        "status": "failed",
                        "conformance_profile": conformance_profile,
                        "error_type": type(e).__name__,
                        "error_message": str(e),
                    }
                )
                continue

        if last_error is not None:
            raise BindingExecutionError(
                (
                    f"Binding execution failed for capability '{capability_id}' after "
                    f"{len(chain)} attempt(s)."
                ),
                capability_id=capability_id,
                cause=last_error,
            ) from last_error

        raise BindingExecutionError(
            f"No executable binding candidates for capability '{capability_id}'.",
            capability_id=capability_id,
        )

    def _build_fallback_chain(self, *, capability_id: str, primary_binding_id: str) -> list[str]:
        """
        Build deterministic fallback chain:

        1. resolved primary binding
        2. optional binding metadata fallback_binding_id chain
        3. mandatory terminal official default binding
        """
        chain: list[str] = []
        visited: set[str] = set()

        current_id = primary_binding_id
        while current_id and current_id not in visited:
            binding = self.binding_registry.get_binding(current_id)
            if binding.capability_id != capability_id:
                break

            chain.append(current_id)
            visited.add(current_id)

            raw_next = binding.metadata.get("fallback_binding_id") if isinstance(binding.metadata, dict) else None
            if not isinstance(raw_next, str) or not raw_next:
                break
            current_id = raw_next

        default_binding_id = self.binding_registry.get_official_default_binding_id(capability_id)
        if isinstance(default_binding_id, str) and default_binding_id and default_binding_id not in visited:
            chain.append(default_binding_id)

        return chain

    def _resolve_conformance_profile(self, metadata: dict[str, Any] | None) -> str:
        if not isinstance(metadata, dict):
            return "standard"
        profile = metadata.get("conformance_profile")
        if isinstance(profile, str) and profile:
            return profile
        return "standard"
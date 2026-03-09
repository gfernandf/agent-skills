from __future__ import annotations

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

    def execute(self, capability, step_input: dict) -> dict:
        """
        Execute a capability using the resolved binding.
        """

        capability_id = capability.id

        try:
            resolved = self.binding_resolver.resolve(capability_id)

            binding = self.binding_registry.get_binding(resolved.binding_id)

            service = self.service_resolver.resolve(binding.service_id)

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

            return mapped_output

        except Exception as e:
            raise BindingExecutionError(
                f"Binding execution failed for capability '{capability_id}'.",
                capability_id=capability_id,
                cause=e,
            ) from e
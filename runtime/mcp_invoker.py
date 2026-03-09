from __future__ import annotations

from typing import Any, Callable, Protocol

from runtime.binding_models import InvocationRequest, InvocationResponse
from runtime.errors import RuntimeErrorBase


class MCPInvocationError(RuntimeErrorBase):
    """Raised when an MCP invocation fails."""


class MCPClient(Protocol):
    """
    Minimal protocol expected by the MCP invoker.

    A concrete integration layer can adapt any MCP SDK/client to this interface.
    """

    def call_tool(self, server: str, tool_name: str, arguments: dict[str, Any]) -> Any:
        ...


class MCPClientRegistry(Protocol):
    """
    Registry/factory that returns an MCP client for a given server id.

    This keeps the invoker independent from any specific MCP transport/runtime.
    """

    def get_client(self, server: str) -> MCPClient:
        ...


class MCPInvoker:
    """
    Execute a binding invocation against an MCP server.

    v1 assumptions:
    - service.server identifies the MCP server
    - binding.operation_id is the MCP tool/function name
    - request.payload becomes the MCP arguments object
    - the returned tool result is surfaced as raw_response
    """

    def __init__(self, client_registry: MCPClientRegistry) -> None:
        self.client_registry = client_registry

    def invoke(self, request: InvocationRequest) -> InvocationResponse:
        service = request.service
        binding = request.binding

        if service.server is None:
            raise MCPInvocationError(
                f"Service '{service.id}' does not define an MCP server.",
                capability_id=request.context_metadata.get("capability_id"),
            )

        try:
            client = self.client_registry.get_client(service.server)
        except Exception as e:
            raise MCPInvocationError(
                f"Could not acquire MCP client for server '{service.server}'.",
                capability_id=request.context_metadata.get("capability_id"),
                cause=e,
            ) from e

        try:
            result = client.call_tool(
                server=service.server,
                tool_name=binding.operation_id,
                arguments=request.payload,
            )
        except Exception as e:
            raise MCPInvocationError(
                f"MCP invocation failed for service '{service.id}' and tool '{binding.operation_id}'.",
                capability_id=request.context_metadata.get("capability_id"),
                cause=e,
            ) from e

        return InvocationResponse(
            status="success",
            raw_response=result,
            metadata={
                "service_id": service.id,
                "server": service.server,
                "tool_name": binding.operation_id,
            },
        )
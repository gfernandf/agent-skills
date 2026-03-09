from __future__ import annotations

from runtime.binding_models import InvocationRequest, InvocationResponse
from runtime.errors import RuntimeErrorBase


class ProtocolRoutingError(RuntimeErrorBase):
    """Raised when an invocation request cannot be routed to a protocol invoker."""


class ProtocolRouter:
    """
    Route an InvocationRequest to the appropriate protocol-specific invoker.

    Supported protocols in v1:
    - openapi
    - mcp
    - openrpc
    - pythoncall
    """

    def __init__(
        self,
        openapi_invoker,
        mcp_invoker,
        openrpc_invoker,
        pythoncall_invoker,
    ) -> None:
        self.openapi_invoker = openapi_invoker
        self.mcp_invoker = mcp_invoker
        self.openrpc_invoker = openrpc_invoker
        self.pythoncall_invoker = pythoncall_invoker

    def invoke(self, request: InvocationRequest) -> InvocationResponse:
        if not isinstance(request.protocol, str) or not request.protocol:
            raise ProtocolRoutingError("Invocation request protocol must be a non-empty string.")

        try:
            if request.protocol == "openapi":
                return self.openapi_invoker.invoke(request)

            if request.protocol == "mcp":
                return self.mcp_invoker.invoke(request)

            if request.protocol == "openrpc":
                return self.openrpc_invoker.invoke(request)

            if request.protocol == "pythoncall":
                return self.pythoncall_invoker.invoke(request)

        except Exception as e:
            raise ProtocolRoutingError(
                f"Protocol routing failed for protocol '{request.protocol}'.",
                cause=e,
            ) from e

        raise ProtocolRoutingError(
            f"Unsupported invocation protocol '{request.protocol}'."
        )
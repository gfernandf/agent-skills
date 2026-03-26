from __future__ import annotations

import json
from typing import Any

import requests

from runtime.binding_models import InvocationRequest, InvocationResponse
from runtime.errors import RuntimeErrorBase


class OpenRPCInvocationError(RuntimeErrorBase):
    """Raised when a JSON-RPC / OpenRPC invocation fails."""


class OpenRPCInvoker:
    """
    Execute a binding invocation against a JSON-RPC / OpenRPC service.
    """

    DEFAULT_TIMEOUT = 30

    def invoke(self, request: InvocationRequest) -> InvocationResponse:
        service = request.service
        binding = request.binding

        if service.base_url is None:
            raise OpenRPCInvocationError(
                f"Service '{service.id}' does not define a base_url.",
                capability_id=request.context_metadata.get("capability_id"),
            )

        rpc_body = {
            "jsonrpc": "2.0",
            "method": binding.operation_id,
            "params": request.payload,
            "id": 1,
        }

        try:
            response = requests.post(
                service.base_url,
                json=rpc_body,
                timeout=self.DEFAULT_TIMEOUT,
            )
        except requests.RequestException as e:
            raise OpenRPCInvocationError(
                f"JSON-RPC request failed for service '{service.id}'.",
                capability_id=request.context_metadata.get("capability_id"),
                cause=e,
            ) from e

        if not response.ok:
            raise OpenRPCInvocationError(
                f"Service '{service.id}' returned HTTP {response.status_code}.",
                capability_id=request.context_metadata.get("capability_id"),
            )

        try:
            body: Any = response.json()
        except json.JSONDecodeError as e:
            raise OpenRPCInvocationError(
                f"Service '{service.id}' returned non-JSON response.",
                capability_id=request.context_metadata.get("capability_id"),
                cause=e,
            ) from e

        if "error" in body:
            raise OpenRPCInvocationError(
                f"JSON-RPC error from service '{service.id}': {body['error']}",
                capability_id=request.context_metadata.get("capability_id"),
            )

        if "result" not in body:
            raise OpenRPCInvocationError(
                f"JSON-RPC response from service '{service.id}' missing 'result'.",
                capability_id=request.context_metadata.get("capability_id"),
            )

        return InvocationResponse(
            status="success",
            raw_response=body["result"],
            metadata={
                "rpc_id": body.get("id"),
                "service_id": service.id,
            },
        )

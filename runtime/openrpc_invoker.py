from __future__ import annotations

import json
from typing import Any

import requests

from runtime.binding_models import InvocationRequest, InvocationResponse
from runtime.errors import RuntimeErrorBase


class OpenAPIInvocationError(RuntimeErrorBase):
    """Raised when an OpenAPI invocation fails."""


class OpenAPIInvoker:
    """
    Execute a binding invocation against an OpenAPI-compatible HTTP service.

    Assumptions for v1:
    - binding.operation_id represents the HTTP path
    - HTTP method defaults to POST unless metadata specifies otherwise
    - payload is sent as JSON
    - response body is expected to be JSON
    """

    DEFAULT_TIMEOUT = 30

    def invoke(self, request: InvocationRequest) -> InvocationResponse:
        service = request.service
        binding = request.binding

        if service.base_url is None:
            raise OpenAPIInvocationError(
                f"Service '{service.id}' does not define a base_url.",
                capability_id=request.context_metadata.get("capability_id"),
            )

        url = self._build_url(service.base_url, binding.operation_id)

        method = binding.metadata.get("method", "POST").upper()

        try:
            response = requests.request(
                method=method,
                url=url,
                json=request.payload,
                timeout=self.DEFAULT_TIMEOUT,
            )
        except requests.RequestException as e:
            raise OpenAPIInvocationError(
                f"HTTP request failed for service '{service.id}'.",
                capability_id=request.context_metadata.get("capability_id"),
                cause=e,
            ) from e

        if not response.ok:
            raise OpenAPIInvocationError(
                f"Service '{service.id}' returned HTTP {response.status_code}.",
                capability_id=request.context_metadata.get("capability_id"),
            )

        try:
            body: Any = response.json()
        except json.JSONDecodeError as e:
            raise OpenAPIInvocationError(
                f"Service '{service.id}' returned non-JSON response.",
                capability_id=request.context_metadata.get("capability_id"),
                cause=e,
            ) from e

        return InvocationResponse(
            status="success",
            raw_response=body,
            metadata={
                "http_status": response.status_code,
                "service_id": service.id,
            },
        )

    def _build_url(self, base_url: str, operation_id: str) -> str:
        base = base_url.rstrip("/")
        path = operation_id.lstrip("/")
        return f"{base}/{path}"
from __future__ import annotations

import importlib
from typing import Any

from runtime.binding_models import InvocationRequest, InvocationResponse
from runtime.errors import RuntimeErrorBase


class PythonCallInvocationError(RuntimeErrorBase):
    """Raised when a pythoncall invocation fails."""


class PythonCallInvoker:
    """
    Execute a binding invocation against a local Python module.

    v1 assumptions:
    - service.module is an importable Python module path
    - binding.operation_id is the callable name exported by that module
    - request.payload is expanded as keyword arguments
    - the callable return value becomes raw_response

    Example:
        service.module = "local_services.pdf_tools"
        binding.operation_id = "read_pdf"

        def read_pdf(path: str) -> dict[str, Any]:
            ...
    """

    def invoke(self, request: InvocationRequest) -> InvocationResponse:
        service = request.service
        binding = request.binding

        capability_id = request.context_metadata.get("capability_id")

        if service.module is None:
            raise PythonCallInvocationError(
                f"Service '{service.id}' does not define a Python module.",
                capability_id=capability_id,
            )

        if not isinstance(request.payload, dict):
            raise PythonCallInvocationError(
                f"PythonCall payload for binding '{binding.id}' must be a mapping.",
                capability_id=capability_id,
            )

        try:
            module = importlib.import_module(service.module)
        except Exception as e:
            raise PythonCallInvocationError(
                f"Could not import Python module '{service.module}' for service '{service.id}'.",
                capability_id=capability_id,
                cause=e,
            ) from e

        try:
            fn = getattr(module, binding.operation_id)
        except AttributeError as e:
            raise PythonCallInvocationError(
                f"Module '{service.module}' does not expose callable '{binding.operation_id}'.",
                capability_id=capability_id,
                cause=e,
            ) from e

        if not callable(fn):
            raise PythonCallInvocationError(
                f"Object '{binding.operation_id}' in module '{service.module}' is not callable.",
                capability_id=capability_id,
            )

        try:
            result = fn(**request.payload)
        except TypeError as e:
            raise PythonCallInvocationError(
                f"Callable '{binding.operation_id}' in module '{service.module}' rejected the provided arguments.",
                capability_id=capability_id,
                cause=e,
            ) from e
        except Exception as e:
            raise PythonCallInvocationError(
                f"Callable '{binding.operation_id}' in module '{service.module}' failed during execution.",
                capability_id=capability_id,
                cause=e,
            ) from e

        return InvocationResponse(
            status="success",
            raw_response=result,
            metadata={
                "service_id": service.id,
                "module": service.module,
                "callable": binding.operation_id,
            },
        )
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from runtime.errors import (
    AttachValidationError,
    CapabilityExecutionError,
    CapabilityNotFoundError,
    FinalOutputValidationError,
    InputMappingError,
    InvalidExecutionOptionsError,
    InvalidCapabilitySpecError,
    InvalidSkillSpecError,
    OutputMappingError,
    ReferenceResolutionError,
    RuntimeErrorBase,
    SkillNotFoundError,
    StepExecutionError,
)


@dataclass(frozen=True)
class HttpErrorContract:
    status_code: int
    code: str
    type: str
    message: str


def map_runtime_error_to_http(error: Exception) -> HttpErrorContract:
    """
    Map runtime errors to a deterministic HTTP-facing contract.

    This mapper is adapter-facing and intentionally conservative:
    - stable error codes
    - no stack traces
    - no nested cause details
    """
    if isinstance(error, (SkillNotFoundError, CapabilityNotFoundError)):
        return HttpErrorContract(
            status_code=404,
            code="not_found",
            type=type(error).__name__,
            message=sanitize_error_message(error),
        )

    if isinstance(error, (InputMappingError, ReferenceResolutionError, OutputMappingError, AttachValidationError)):
        return HttpErrorContract(
            status_code=400,
            code="invalid_request",
            type=type(error).__name__,
            message=sanitize_error_message(error),
        )

    if isinstance(error, InvalidExecutionOptionsError):
        return HttpErrorContract(
            status_code=400,
            code="invalid_request",
            type=type(error).__name__,
            message=sanitize_error_message(error),
        )

    if isinstance(error, (FinalOutputValidationError, InvalidSkillSpecError, InvalidCapabilitySpecError)):
        return HttpErrorContract(
            status_code=409,
            code="invalid_configuration",
            type=type(error).__name__,
            message=sanitize_error_message(error),
        )

    if isinstance(error, (CapabilityExecutionError, StepExecutionError)):
        lowered = str(error).lower()
        if "required conformance profile" in lowered and "no bindings satisfy" in lowered:
            return HttpErrorContract(
                status_code=412,
                code="conformance_unmet",
                type=type(error).__name__,
                message="No eligible binding satisfies the requested conformance profile.",
            )

        root = _root_cause(error)
        root_name = type(root).__name__.lower()
        if "timeout" in root_name:
            return HttpErrorContract(
                status_code=504,
                code="upstream_timeout",
                type=type(error).__name__,
                message="Upstream service timed out.",
            )
        return HttpErrorContract(
            status_code=502,
            code="upstream_failure",
            type=type(error).__name__,
            message="Upstream service invocation failed.",
        )

    if isinstance(error, RuntimeErrorBase):
        return HttpErrorContract(
            status_code=500,
            code="runtime_error",
            type=type(error).__name__,
            message="Runtime execution failed.",
        )

    return HttpErrorContract(
        status_code=500,
        code="internal_error",
        type=type(error).__name__,
        message="Internal server error.",
    )


def sanitize_error_message(error: Exception, *, max_len: int = 240) -> str:
    raw = str(error) if str(error) else type(error).__name__
    compact = " ".join(raw.split())
    return compact[:max_len]


def build_http_error_payload(error: Exception, trace_id: str | None) -> dict[str, Any]:
    contract = map_runtime_error_to_http(error)
    return {
        "error": {
            "code": contract.code,
            "message": contract.message,
            "type": contract.type,
        },
        "trace_id": trace_id,
    }


def _root_cause(error: Exception) -> Exception:
    current: Exception = error
    for _ in range(8):
        cause = getattr(current, "cause", None)
        if cause is None or not isinstance(cause, Exception):
            return current
        current = cause
    return current

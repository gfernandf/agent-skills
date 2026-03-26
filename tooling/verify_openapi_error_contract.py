#!/usr/bin/env python3
"""Verify deterministic OpenAPI HTTP error contract mapping."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from runtime.errors import (  # noqa: E402
    CapabilityExecutionError,
    CapabilityNotFoundError,
    FinalOutputValidationError,
    InputMappingError,
    SkillNotFoundError,
)
from runtime.openapi_error_contract import map_runtime_error_to_http  # noqa: E402


class FakeTimeoutError(TimeoutError):
    pass


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    checks = 0

    not_found = map_runtime_error_to_http(SkillNotFoundError("skill missing"))
    checks += 1
    _assert(
        not_found.status_code == 404 and not_found.code == "not_found",
        "not_found mapping mismatch",
    )

    invalid_request = map_runtime_error_to_http(InputMappingError("bad input"))
    checks += 1
    _assert(
        invalid_request.status_code == 400
        and invalid_request.code == "invalid_request",
        "invalid_request mapping mismatch",
    )

    invalid_configuration = map_runtime_error_to_http(
        FinalOutputValidationError("missing output")
    )
    checks += 1
    _assert(
        invalid_configuration.status_code == 409
        and invalid_configuration.code == "invalid_configuration",
        "invalid_configuration mapping mismatch",
    )

    upstream_timeout = map_runtime_error_to_http(
        CapabilityExecutionError(
            "upstream timeout", cause=FakeTimeoutError("timed out")
        )
    )
    checks += 1
    _assert(
        upstream_timeout.status_code == 504
        and upstream_timeout.code == "upstream_timeout",
        "upstream_timeout mapping mismatch",
    )

    upstream_failure = map_runtime_error_to_http(
        CapabilityExecutionError("upstream failed", cause=RuntimeError("boom"))
    )
    checks += 1
    _assert(
        upstream_failure.status_code == 502
        and upstream_failure.code == "upstream_failure",
        "upstream_failure mapping mismatch",
    )

    fallback = map_runtime_error_to_http(ValueError("x"))
    checks += 1
    _assert(
        fallback.status_code == 500 and fallback.code == "internal_error",
        "fallback mapping mismatch",
    )

    capability_not_found = map_runtime_error_to_http(
        CapabilityNotFoundError("cap missing")
    )
    checks += 1
    _assert(
        capability_not_found.status_code == 404
        and capability_not_found.code == "not_found",
        "capability not_found mapping mismatch",
    )

    print(f"OpenAPI error contract verification passed ({checks} checks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

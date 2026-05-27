#!/usr/bin/env python3
"""Verify deterministic OpenAPI HTTP error contract mapping."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from runtime.errors import (  # noqa: E402
    CapabilityExecutionError,
    CapabilityNotFoundError,
    FinalOutputValidationError,
    IdempotencyConflictError,
    InputMappingError,
    SkillNotFoundError,
)
from runtime.openapi_error_contract import map_runtime_error_to_http  # noqa: E402


class FakeTimeoutError(TimeoutError):
    pass


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _assert_common_auth_responses(
    responses: dict[str, dict[str, str]],
    *,
    path_label: str,
) -> int:
    expected = {
        "401": "Missing API key",
        "403": "Invalid API key",
        "429": "Rate limited",
    }
    checks = 0
    for status, description in expected.items():
        checks += 1
        actual = responses.get(status, {}).get("description")
        _assert(
            actual == description,
            f"openapi {path_label} {status} description mismatch",
        )
    return checks


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
        fallback.status_code == 400 and fallback.code == "invalid_request",
        "fallback mapping mismatch",
    )

    idempotency_conflict = map_runtime_error_to_http(
        IdempotencyConflictError("duplicate key payload mismatch")
    )
    checks += 1
    _assert(
        idempotency_conflict.status_code == 409
        and idempotency_conflict.code == "idempotency_conflict",
        "idempotency_conflict mapping mismatch",
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

    spec_path = ROOT / "docs" / "specs" / "consumer_facing_v1_openapi.json"
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    paths = spec.get("paths", {})
    schemas = spec.get("components", {}).get("schemas", {})

    metrics_get = paths.get("/v1/metrics", {}).get("get", {})
    metrics_responses = metrics_get.get("responses", {})
    metrics_200 = metrics_responses.get("200", {})
    metrics_content = metrics_200.get("content", {})
    checks += 1
    _assert(
        metrics_content.get("application/json", {}).get("schema", {}).get("$ref")
        == "#/components/schemas/MetricsSnapshot",
        "openapi /v1/metrics application/json contract mismatch",
    )
    checks += _assert_common_auth_responses(
        metrics_responses,
        path_label="/v1/metrics",
    )

    prom_get = paths.get("/v1/metrics/prometheus", {}).get("get", {})
    prom_responses = prom_get.get("responses", {})
    prom_200 = prom_responses.get("200", {})
    prom_content = prom_200.get("content", {})
    checks += 1
    _assert(
        prom_content.get("text/plain", {}).get("schema", {}).get("type") == "string",
        "openapi /v1/metrics/prometheus text/plain contract mismatch",
    )
    checks += _assert_common_auth_responses(
        prom_responses,
        path_label="/v1/metrics/prometheus",
    )

    checks += 1
    _assert(
        "MetricsSnapshot" in schemas and "MetricHistogramSummary" in schemas,
        "openapi metrics schemas missing",
    )

    print(f"OpenAPI error contract verification passed ({checks} checks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import json
from pathlib import Path


SPEC_PATH = (
    Path(__file__).resolve().parent
    / "docs"
    / "specs"
    / "consumer_facing_v1_openapi.json"
)


def test_consumer_openapi_includes_async_run_routes() -> None:
    spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    paths = spec.get("paths", {})

    expected_paths = {
        "/v1/run_async",
        "/run_async",
        "/v1/runs/{run_id}/cancel",
        "/v1/runs/{run_id}/checkpoints",
        "/v1/runs/{run_id}/resume",
        "/v1/runs/{run_id}/approve",
        "/v1/runs/{run_id}/deny",
        "/v1/runs/{run_id}/replay",
        "/v1/runs/{run_id}/fork",
        "/v1/metrics",
        "/v1/metrics/prometheus",
    }
    assert expected_paths.issubset(paths.keys())

    fork_path = paths["/v1/runs/{run_id}/fork"]
    assert "post" in fork_path
    assert fork_path["post"]["operationId"] == "forkRun"

    schemas = spec["components"]["schemas"]

    fork_schema = schemas["ForkRunResponse"]
    assert "run" in fork_schema["properties"]
    assert "fork" in fork_schema["properties"]

    assert "ResumeRunResponse" in schemas
    assert "ReplayRunResponse" in schemas
    assert "CheckpointsListResponse" in schemas

    run_async_props = schemas["RunAsyncRequest"]["properties"]
    assert "idempotency_key" in run_async_props

    execute_async_responses = paths["/v1/skills/{skill_id}/execute/async"]["post"][
        "responses"
    ]
    run_async_v1_responses = paths["/v1/run_async"]["post"]["responses"]
    run_async_legacy_responses = paths["/run_async"]["post"]["responses"]
    assert "409" in execute_async_responses
    assert "409" in run_async_v1_responses
    assert "409" in run_async_legacy_responses

    run_status_enum = schemas["RunStatus"]["properties"]["status"]["enum"]
    assert "waiting_for_human" in run_status_enum
    assert "replaying" in run_status_enum
    assert "canceled" in run_status_enum


def test_consumer_openapi_metrics_contract_is_explicit() -> None:
    spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    paths = spec.get("paths", {})
    schemas = spec["components"]["schemas"]

    metrics_get = paths["/v1/metrics"]["get"]
    metrics_200 = metrics_get["responses"]["200"]
    assert "content" in metrics_200
    assert "application/json" in metrics_200["content"]
    assert (
        metrics_200["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/MetricsSnapshot"
    )

    prom_get = paths["/v1/metrics/prometheus"]["get"]
    prom_200 = prom_get["responses"]["200"]
    assert "content" in prom_200
    assert "text/plain" in prom_200["content"]
    assert prom_200["content"]["text/plain"]["schema"]["type"] == "string"

    assert "MetricsSnapshot" in schemas
    assert "MetricHistogramSummary" in schemas

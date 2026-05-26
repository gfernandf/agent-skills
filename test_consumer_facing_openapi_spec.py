from __future__ import annotations

import json
from pathlib import Path


SPEC_PATH = Path(__file__).resolve().parent / "docs" / "specs" / "consumer_facing_v1_openapi.json"


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

    run_status_enum = schemas["RunStatus"]["properties"]["status"]["enum"]
    assert "waiting_for_human" in run_status_enum
    assert "replaying" in run_status_enum
    assert "canceled" in run_status_enum

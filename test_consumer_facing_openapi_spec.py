from __future__ import annotations

import json
from pathlib import Path


SPEC_PATH = Path(__file__).resolve().parent / "docs" / "specs" / "consumer_facing_v1_openapi.json"


def test_consumer_openapi_includes_fork_route() -> None:
    spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    paths = spec.get("paths", {})

    assert "/v1/runs/{run_id}/fork" in paths

    fork_path = paths["/v1/runs/{run_id}/fork"]
    assert "post" in fork_path
    assert fork_path["post"]["operationId"] == "forkRun"

    fork_schema = spec["components"]["schemas"]["ForkRunResponse"]
    assert "run" in fork_schema["properties"]
    assert "fork" in fork_schema["properties"]

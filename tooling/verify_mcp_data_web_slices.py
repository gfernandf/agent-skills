#!/usr/bin/env python3

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
REGISTRY_ROOT = ROOT.parent / "agent-skill-registry"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from customer_facing.neutral_api import NeutralRuntimeAPI
from official_services.data_baseline import validate_schema
from official_services.web_baseline import fetch_webpage


_DATA_BINDING_ID = "mcp_data_schema_validate_inprocess"
_DATA_SERVICE_ID = "data_mcp_inprocess"
_WEB_BINDING_ID = "mcp_web_fetch_inprocess"
_WEB_SERVICE_ID = "web_mcp_inprocess"


def _write_active_bindings(host_root: Path) -> None:
    state_dir = host_root / ".agent-skills"
    state_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "data.schema.validate": _DATA_BINDING_ID,
        "web.page.fetch": _WEB_BINDING_ID,
    }
    (state_dir / "active_bindings.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _assert_mcp_result(
    result: dict, expected_outputs: dict, expected_binding: str, expected_service: str
) -> None:
    outputs = result.get("outputs")
    meta = result.get("meta", {})

    if outputs != expected_outputs:
        raise RuntimeError(
            f"MCP output mismatch. expected={expected_outputs!r} actual={outputs!r}"
        )

    if meta.get("binding_id") != expected_binding:
        raise RuntimeError(
            f"Expected binding_id '{expected_binding}', got '{meta.get('binding_id')}'."
        )

    if meta.get("service_id") != expected_service:
        raise RuntimeError(
            f"Expected service_id '{expected_service}', got '{meta.get('service_id')}'."
        )


def main() -> int:
    schema_input = {
        "data": {"name": "MCP", "version": 1},
        "schema": {
            "type": "object",
            "required": ["name"],
        },
    }
    # Deterministic invalid URL path avoids external network dependency in CI.
    web_input = {"url": "ftp://example.com"}

    expected_data = validate_schema(**schema_input)
    expected_web = fetch_webpage(**web_input)

    with tempfile.TemporaryDirectory(prefix="agent-skills-mcp-") as tmpdir:
        host_root = Path(tmpdir)
        _write_active_bindings(host_root)

        api = NeutralRuntimeAPI(
            registry_root=REGISTRY_ROOT,
            runtime_root=ROOT,
            host_root=host_root,
        )

        data_result = api.execute_capability("data.schema.validate", schema_input)
        _assert_mcp_result(
            data_result,
            expected_outputs=expected_data,
            expected_binding=_DATA_BINDING_ID,
            expected_service=_DATA_SERVICE_ID,
        )

        web_result = api.execute_capability("web.page.fetch", web_input)
        _assert_mcp_result(
            web_result,
            expected_outputs=expected_web,
            expected_binding=_WEB_BINDING_ID,
            expected_service=_WEB_SERVICE_ID,
        )

    print("MCP data/web slice verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

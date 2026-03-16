#!/usr/bin/env python3

from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
REGISTRY_ROOT = ROOT.parent / "agent-skill-registry"
SNAPSHOT_PATH = ROOT / "tooling" / "snapshots" / "consumer_facing_parity_v1.json"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from customer_facing.mcp_tool_bridge import MCPToolBridge
from customer_facing.neutral_api import NeutralRuntimeAPI
from gateway.core import SkillGateway


def _http_get_json(url: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
    req = urllib.request.Request(url, headers=headers or {}, method="GET")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _http_post_json(url: str, payload: dict[str, Any], headers: dict[str, str] | None = None) -> dict[str, Any]:
    req_headers = {"Content-Type": "application/json"}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=req_headers,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _normalize(value: Any) -> Any:
    if isinstance(value, dict):
        # Ignore volatile observability/enrichment fields that are not part of parity contract semantics.
        ignored_keys = {
            "trace_id",
            "timestamp",
            "runtime_root",
            "registry_root",
            "host_root",
            "attempts",
            "fallback_chain",
            "fallback_used",
            "resolution_plan",
            "conformance_profile",
            "required_conformance_profile",
        }
        return {
            k: _normalize(v)
            for k, v in sorted(value.items(), key=lambda kv: kv[0])
            if k not in ignored_keys
        }
    if isinstance(value, list):
        return [_normalize(x) for x in value]
    return value


def _compute_snapshot(api_key: str) -> dict[str, Any]:
    api = NeutralRuntimeAPI(
        registry_root=REGISTRY_ROOT,
        runtime_root=ROOT,
        host_root=ROOT,
    )
    gateway = SkillGateway(
        registry_root=REGISTRY_ROOT,
        runtime_root=ROOT,
        host_root=ROOT,
    )
    bridge = MCPToolBridge(api, gateway)

    headers = {"x-api-key": api_key}

    http_health = _http_get_json("http://127.0.0.1:8086/v1/health")
    mcp_health = bridge.call_tool("runtime.health", {})

    http_desc = _http_get_json(
        "http://127.0.0.1:8086/v1/skills/agent.plan-from-objective/describe",
        headers=headers,
    )
    mcp_desc = bridge.call_tool("skill.describe", {"skill_id": "agent.plan-from-objective"})

    skill_inputs = {"objective": "Build a policy-compliant execution plan."}
    http_skill_exec = _http_post_json(
        "http://127.0.0.1:8086/v1/skills/agent.plan-from-objective/execute",
        {"inputs": skill_inputs, "include_trace": False},
        headers=headers,
    )
    mcp_skill_exec = bridge.call_tool(
        "skill.execute",
        {"skill_id": "agent.plan-from-objective", "inputs": skill_inputs, "include_trace": False},
    )

    capability_inputs = {
        "payload": {"title": "Hello"},
        "constraint": {"required_keys": ["title"], "forbidden_keys": ["password"]},
    }
    http_cap_exec = _http_post_json(
        "http://127.0.0.1:8086/v1/capabilities/policy.constraint.validate/execute",
        {"inputs": capability_inputs},
        headers=headers,
    )
    mcp_cap_exec = bridge.call_tool(
        "capability.execute",
        {"capability_id": "policy.constraint.validate", "inputs": capability_inputs},
    )

    snapshot = {
        "health": {
            "http": _normalize(http_health),
            "mcp": _normalize(mcp_health),
            "equal": _normalize(http_health) == _normalize(mcp_health),
        },
        "describe_skill": {
            "http": _normalize(http_desc),
            "mcp": _normalize(mcp_desc),
            "equal": _normalize(http_desc) == _normalize(mcp_desc),
        },
        "execute_skill": {
            "http": _normalize(http_skill_exec),
            "mcp": _normalize(mcp_skill_exec),
            "equal": _normalize(http_skill_exec) == _normalize(mcp_skill_exec),
        },
        "execute_capability": {
            "http": _normalize(http_cap_exec),
            "mcp": _normalize(mcp_cap_exec),
            "equal": _normalize(http_cap_exec) == _normalize(mcp_cap_exec),
        },
    }

    snapshot["all_equal"] = all(section.get("equal") for section in snapshot.values() if isinstance(section, dict) and "equal" in section)
    return snapshot


def main() -> int:
    api_key = "parity-key"
    proc = subprocess.Popen(
        [
            sys.executable,
            str(ROOT / "tooling" / "run_customer_http_api.py"),
            "--host",
            "127.0.0.1",
            "--port",
            "8086",
            "--runtime-root",
            str(ROOT),
            "--registry-root",
            str(REGISTRY_ROOT),
            "--api-key",
            api_key,
            "--rate-limit-requests",
            "120",
            "--rate-limit-window-seconds",
            "60",
        ]
    )

    try:
        time.sleep(0.8)
        actual = _compute_snapshot(api_key)

        if not actual.get("all_equal"):
            raise RuntimeError("HTTP and MCP outputs diverge for at least one operation.")

        if SNAPSHOT_PATH.exists():
            expected = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
            if actual != expected:
                diff_path = SNAPSHOT_PATH.with_suffix(".actual.json")
                diff_path.write_text(json.dumps(actual, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                raise RuntimeError(
                    "Parity snapshot mismatch. "
                    f"Expected snapshot in {SNAPSHOT_PATH.name}; actual written to {diff_path.name}."
                )
        else:
            SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
            SNAPSHOT_PATH.write_text(json.dumps(actual, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

        print("Customer-facing parity snapshot verification passed.")
        return 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())

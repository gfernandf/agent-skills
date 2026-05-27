#!/usr/bin/env python3

from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
REGISTRY_ROOT = ROOT.parent / "agent-skill-registry"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from customer_facing.mcp_tool_bridge import MCPToolBridge
from customer_facing.neutral_api import NeutralRuntimeAPI
from gateway.core import SkillGateway


def _http_get_json(url: str, headers: dict[str, str] | None = None) -> dict:
    req = urllib.request.Request(url, headers=headers or {}, method="GET")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _http_post_json(
    url: str,
    payload: dict,
    *,
    headers: dict[str, str] | None = None,
) -> dict:
    data = json.dumps(payload).encode("utf-8")
    request_headers = {"Content-Type": "application/json"}
    if headers:
        request_headers.update(headers)
    req = urllib.request.Request(
        url, data=data, headers=request_headers, method="POST"
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _wait_for_server_ready(base_url: str, *, timeout_seconds: float = 20.0) -> None:
    deadline = time.time() + timeout_seconds
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            health = _http_get_json(f"{base_url}/v1/health")
            if isinstance(health, dict) and health.get("status") == "ok":
                return
        except Exception as exc:  # pragma: no cover - exercised in integration runs
            last_error = exc
        time.sleep(0.2)
    raise RuntimeError(f"server did not become ready at {base_url}: {last_error}")


def _pick_skill(base_url: str, *, headers: dict[str, str]) -> str:
    listed = _http_get_json(f"{base_url}/v1/skills/list", headers=headers)
    skills = listed.get("skills") if isinstance(listed, dict) else None
    if not isinstance(skills, list):
        raise RuntimeError("skills/list did not return a skills array")

    available = {
        item.get("id")
        for item in skills
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    preferred = [
        "agent.plan-and-route",
        "agent.execute-from-plan",
        "agent.orchestrate-from-prompt",
    ]
    for skill_id in preferred:
        if skill_id in available:
            return skill_id
    raise RuntimeError(f"none of preferred verification skills found: {preferred}")


def main() -> int:
    base_url = "http://127.0.0.1:8083"
    api_key = "neutral-verify-key"
    headers = {"x-api-key": api_key}
    http_proc = subprocess.Popen(
        [
            sys.executable,
            str(ROOT / "tooling" / "run_customer_http_api.py"),
            "--host",
            "127.0.0.1",
            "--port",
            "8083",
            "--runtime-root",
            str(ROOT),
            "--registry-root",
            str(REGISTRY_ROOT),
            "--api-key",
            api_key,
        ],
    )

    try:
        _wait_for_server_ready(base_url)
        skill_id = _pick_skill(base_url, headers=headers)

        health = _http_get_json(f"{base_url}/v1/health")
        if health.get("status") != "ok":
            raise RuntimeError("health endpoint did not return status=ok")

        desc = _http_get_json(
            f"{base_url}/v1/skills/{skill_id}/describe",
            headers=headers,
        )
        if desc.get("id") != skill_id:
            raise RuntimeError("describe endpoint returned unexpected skill id")

        exec_result = _http_post_json(
            f"{base_url}/v1/skills/{skill_id}/execute",
            {
                "inputs": {
                    "objective": "Build a safe runtime execution plan.",
                },
                "include_trace": False,
            },
            headers=headers,
        )
        if "outputs" not in exec_result:
            raise RuntimeError("execute endpoint did not return outputs")

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
        tools = bridge.list_tools()
        if not any(t.get("name") == "skill.execute" for t in tools):
            raise RuntimeError("MCP bridge did not expose skill.execute")

        mcp_exec = bridge.call_tool(
            "skill.execute",
            {
                "skill_id": skill_id,
                "inputs": {
                    "objective": "Generate a compact plan.",
                },
            },
        )
        if "outputs" not in mcp_exec:
            raise RuntimeError("MCP bridge execution did not return outputs")

        print("Consumer-facing neutral verification passed.")
        return 0
    finally:
        http_proc.terminate()
        try:
            http_proc.wait(timeout=5)
        except Exception:
            http_proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())

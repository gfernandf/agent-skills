#!/usr/bin/env python3

from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
REGISTRY_ROOT = ROOT.parent / "agent-skill-registry"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from customer_facing.mcp_tool_bridge import MCPToolBridge
from customer_facing.neutral_api import NeutralRuntimeAPI


def _http_get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _http_post_json(url: str, payload: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    http_proc = subprocess.Popen(
        [
            "python",
            str(ROOT / "tooling" / "run_customer_http_api.py"),
            "--host",
            "127.0.0.1",
            "--port",
            "8083",
            "--runtime-root",
            str(ROOT),
            "--registry-root",
            str(REGISTRY_ROOT),
        ],
    )

    try:
        time.sleep(0.7)

        health = _http_get_json("http://127.0.0.1:8083/v1/health")
        if health.get("status") != "ok":
            raise RuntimeError("health endpoint did not return status=ok")

        desc = _http_get_json("http://127.0.0.1:8083/v1/skills/agent.plan-from-objective/describe")
        if desc.get("id") != "agent.plan-from-objective":
            raise RuntimeError("describe endpoint returned unexpected skill id")

        exec_result = _http_post_json(
            "http://127.0.0.1:8083/v1/skills/agent.plan-from-objective/execute",
            {
                "inputs": {
                    "objective": "Build a safe runtime execution plan.",
                },
                "include_trace": False,
            },
        )
        if "outputs" not in exec_result:
            raise RuntimeError("execute endpoint did not return outputs")

        api = NeutralRuntimeAPI(
            registry_root=REGISTRY_ROOT,
            runtime_root=ROOT,
            host_root=ROOT,
        )
        bridge = MCPToolBridge(api)
        tools = bridge.list_tools()
        if not any(t.get("name") == "skill.execute" for t in tools):
            raise RuntimeError("MCP bridge did not expose skill.execute")

        mcp_exec = bridge.call_tool(
            "skill.execute",
            {
                "skill_id": "agent.plan-from-objective",
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

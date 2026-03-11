from __future__ import annotations

import json
import sys
from typing import Any

from customer_facing.neutral_api import NeutralRuntimeAPI
from runtime.openapi_error_contract import map_runtime_error_to_http


class MCPToolBridge:
    """
    MCP-oriented adapter over the neutral runtime API.

    This bridge exposes stable tool names that can be hosted by any concrete
    MCP server transport implementation.
    """

    def __init__(self, api: NeutralRuntimeAPI) -> None:
        self.api = api

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "runtime.health",
                "description": "Get runtime health information.",
                "input_schema": {"type": "object", "properties": {}},
            },
            {
                "name": "skill.describe",
                "description": "Describe a skill contract and steps.",
                "input_schema": {
                    "type": "object",
                    "required": ["skill_id"],
                    "properties": {
                        "skill_id": {"type": "string"},
                    },
                },
            },
            {
                "name": "skill.execute",
                "description": "Execute a skill with structured inputs.",
                "input_schema": {
                    "type": "object",
                    "required": ["skill_id"],
                    "properties": {
                        "skill_id": {"type": "string"},
                        "inputs": {"type": "object"},
                        "trace_id": {"type": "string"},
                        "include_trace": {"type": "boolean"},
                    },
                },
            },
            {
                "name": "capability.execute",
                "description": "Execute a capability directly with structured inputs.",
                "input_schema": {
                    "type": "object",
                    "required": ["capability_id"],
                    "properties": {
                        "capability_id": {"type": "string"},
                        "inputs": {"type": "object"},
                        "trace_id": {"type": "string"},
                    },
                },
            },
        ]

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        args = arguments or {}

        if name == "runtime.health":
            return self.api.health()

        if name == "skill.describe":
            return self.api.describe_skill(str(args.get("skill_id", "")))

        if name == "skill.execute":
            return self.api.execute_skill(
                skill_id=str(args.get("skill_id", "")),
                inputs=args.get("inputs") if isinstance(args.get("inputs"), dict) else {},
                trace_id=args.get("trace_id") if isinstance(args.get("trace_id"), str) else None,
                include_trace=bool(args.get("include_trace", False)),
            )

        if name == "capability.execute":
            return self.api.execute_capability(
                capability_id=str(args.get("capability_id", "")),
                inputs=args.get("inputs") if isinstance(args.get("inputs"), dict) else {},
                trace_id=args.get("trace_id") if isinstance(args.get("trace_id"), str) else None,
            )

        raise ValueError(f"Unsupported MCP tool '{name}'")


def run_stdio_bridge(bridge: MCPToolBridge) -> int:
    """
    Lightweight JSON-RPC-like stdio loop useful as a transport-neutral bridge.

    Request line format:
      {"id": "1", "method": "tools/list"}
      {"id": "2", "method": "tools/call", "params": {"name": "skill.execute", "arguments": {...}}}
    """
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue

        try:
            req = json.loads(line)
            req_id = req.get("id")
            method = req.get("method")
            params = req.get("params", {})

            if method == "tools/list":
                result = {"tools": bridge.list_tools()}
            elif method == "tools/call":
                name = params.get("name")
                arguments = params.get("arguments", {})
                if not isinstance(name, str):
                    raise ValueError("tools/call requires string param 'name'")
                if not isinstance(arguments, dict):
                    raise ValueError("tools/call param 'arguments' must be an object")
                result = bridge.call_tool(name=name, arguments=arguments)
            else:
                raise ValueError(f"Unsupported method '{method}'")

            out = {"id": req_id, "result": result}
        except Exception as e:
            contract = map_runtime_error_to_http(e)
            out = {
                "id": req.get("id") if isinstance(req, dict) else None,
                "error": {
                    "code": contract.code,
                    "message": contract.message,
                    "type": contract.type,
                    "status": contract.status_code,
                },
            }

        sys.stdout.write(json.dumps(out, ensure_ascii=False) + "\n")
        sys.stdout.flush()

    return 0

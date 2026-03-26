from __future__ import annotations

import json
import sys
from typing import Any

from customer_facing.neutral_api import NeutralRuntimeAPI
from gateway.core import SkillGateway
from runtime.openapi_error_contract import map_runtime_error_to_http


class MCPToolBridge:
    """
    MCP-oriented adapter over the neutral runtime API.

    This bridge exposes stable tool names that can be hosted by any concrete
    MCP server transport implementation.
    """

    def __init__(self, api: NeutralRuntimeAPI, gateway: SkillGateway) -> None:
        self.api = api
        self.gateway = gateway

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
                "name": "skill.list",
                "description": "List available skills with optional filters.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "domain": {"type": "string"},
                        "role": {"type": "string"},
                        "status": {"type": "string"},
                        "invocation": {"type": "string"},
                    },
                },
            },
            {
                "name": "skill.discover",
                "description": "Discover and rank skills for a user intent.",
                "input_schema": {
                    "type": "object",
                    "required": ["intent"],
                    "properties": {
                        "intent": {"type": "string"},
                        "domain": {"type": "string"},
                        "role": {"type": "string"},
                        "limit": {"type": "integer"},
                    },
                },
            },
            {
                "name": "skill.diagnostics",
                "description": "Return gateway diagnostics including cache stats.",
                "input_schema": {
                    "type": "object",
                    "properties": {},
                },
            },
            {
                "name": "skill.metrics.reset",
                "description": "Reset gateway diagnostics metrics and optionally clear caches.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "clear_cache": {"type": "boolean"},
                    },
                },
            },
            {
                "name": "skill.attach",
                "description": "Attach a skill to a target and execute it.",
                "input_schema": {
                    "type": "object",
                    "required": ["skill_id", "target_type", "target_ref"],
                    "properties": {
                        "skill_id": {"type": "string"},
                        "target_type": {"type": "string"},
                        "target_ref": {"type": "string"},
                        "inputs": {"type": "object"},
                        "trace_id": {"type": "string"},
                        "include_trace": {"type": "boolean"},
                        "required_conformance_profile": {"type": "string"},
                        "audit_mode": {"type": "string"},
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
                        "required_conformance_profile": {"type": "string"},
                        "audit_mode": {"type": "string"},
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
                        "required_conformance_profile": {"type": "string"},
                    },
                },
            },
            {
                "name": "capability.explain",
                "description": "Explain effective binding resolution and conformance eligibility for a capability.",
                "input_schema": {
                    "type": "object",
                    "required": ["capability_id"],
                    "properties": {
                        "capability_id": {"type": "string"},
                        "required_conformance_profile": {"type": "string"},
                    },
                },
            },
            {
                "name": "skill.governance.list",
                "description": "List skills by governance state from operational quality catalog.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "min_state": {"type": "string"},
                        "limit": {"type": "integer"},
                    },
                },
            },
        ]

    def call_tool(
        self, name: str, arguments: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        args = arguments or {}

        if name == "runtime.health":
            return self.api.health()

        if name == "skill.describe":
            return self.api.describe_skill(str(args.get("skill_id", "")))

        if name == "skill.list":
            return {
                "skills": [
                    s.to_dict()
                    for s in self.gateway.list_skills(
                        domain=args.get("domain")
                        if isinstance(args.get("domain"), str)
                        else None,
                        role=args.get("role")
                        if isinstance(args.get("role"), str)
                        else None,
                        status=args.get("status")
                        if isinstance(args.get("status"), str)
                        else None,
                        invocation=args.get("invocation")
                        if isinstance(args.get("invocation"), str)
                        else None,
                    )
                ]
            }

        if name == "skill.discover":
            intent = args.get("intent")
            if not isinstance(intent, str) or not intent:
                raise ValueError(
                    "skill.discover requires non-empty string argument 'intent'"
                )
            limit = (
                int(args.get("limit", 10)) if isinstance(args.get("limit"), int) else 10
            )
            return {
                "intent": intent,
                "results": [
                    r.to_dict()
                    for r in self.gateway.discover(
                        intent=intent,
                        domain=args.get("domain")
                        if isinstance(args.get("domain"), str)
                        else None,
                        role_filter=args.get("role")
                        if isinstance(args.get("role"), str)
                        else None,
                        limit=limit,
                    )
                ],
            }

        if name == "skill.diagnostics":
            return self.gateway.diagnostics()

        if name == "skill.metrics.reset":
            return self.gateway.reset_diagnostics_metrics(
                clear_cache=bool(args.get("clear_cache", False))
            )

        if name == "skill.attach":
            target_type = args.get("target_type")
            target_ref = args.get("target_ref")
            if not isinstance(target_type, str) or not target_type:
                raise ValueError(
                    "skill.attach requires non-empty string argument 'target_type'"
                )
            if not isinstance(target_ref, str) or not target_ref:
                raise ValueError(
                    "skill.attach requires non-empty string argument 'target_ref'"
                )

            result = self.gateway.attach(
                skill_id=str(args.get("skill_id", "")),
                target_type=target_type,
                target_ref=target_ref,
                inputs=args.get("inputs")
                if isinstance(args.get("inputs"), dict)
                else {},
                trace_id=args.get("trace_id")
                if isinstance(args.get("trace_id"), str)
                else None,
                include_trace=bool(args.get("include_trace", False)),
                required_conformance_profile=(
                    args.get("required_conformance_profile")
                    if isinstance(args.get("required_conformance_profile"), str)
                    else None
                ),
                audit_mode=(
                    args.get("audit_mode")
                    if isinstance(args.get("audit_mode"), str)
                    else None
                ),
            )
            return result.to_dict()

        if name == "skill.execute":
            return self.api.execute_skill(
                skill_id=str(args.get("skill_id", "")),
                inputs=args.get("inputs")
                if isinstance(args.get("inputs"), dict)
                else {},
                trace_id=args.get("trace_id")
                if isinstance(args.get("trace_id"), str)
                else None,
                include_trace=bool(args.get("include_trace", False)),
                required_conformance_profile=(
                    args.get("required_conformance_profile")
                    if isinstance(args.get("required_conformance_profile"), str)
                    else None
                ),
                audit_mode=(
                    args.get("audit_mode")
                    if isinstance(args.get("audit_mode"), str)
                    else None
                ),
                execution_channel="mcp",
            )

        if name == "capability.execute":
            return self.api.execute_capability(
                capability_id=str(args.get("capability_id", "")),
                inputs=args.get("inputs")
                if isinstance(args.get("inputs"), dict)
                else {},
                trace_id=args.get("trace_id")
                if isinstance(args.get("trace_id"), str)
                else None,
                required_conformance_profile=(
                    args.get("required_conformance_profile")
                    if isinstance(args.get("required_conformance_profile"), str)
                    else None
                ),
            )

        if name == "capability.explain":
            return self.api.explain_capability_resolution(
                capability_id=str(args.get("capability_id", "")),
                required_conformance_profile=(
                    args.get("required_conformance_profile")
                    if isinstance(args.get("required_conformance_profile"), str)
                    else None
                ),
            )

        if name == "skill.governance.list":
            return self.api.list_skill_governance(
                min_state=args.get("min_state")
                if isinstance(args.get("min_state"), str)
                else None,
                limit=int(args.get("limit", 20))
                if isinstance(args.get("limit"), int)
                else 20,
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

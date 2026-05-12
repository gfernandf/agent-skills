"""
External ORCA agent (OpenAI API + ORCA HTTP API).

This script is designed for third-party integrations outside VS Code.
It enforces that the assistant executes at least one ORCA skill before
returning a final answer.

Environment variables:
  OPENAI_API_KEY   Required
  ORCA_BASE_URL    Optional (default: http://127.0.0.1:8080)
  ORCA_API_KEY     Optional (set if ORCA server requires x-api-key)
  OPENAI_MODEL     Optional (default: gpt-4.1-mini)

Usage:
  python examples/orca_external_agent.py "Necesito un plan de trabajo para lanzar un agente"
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from openai import OpenAI


ORCA_BASE_URL = os.getenv("ORCA_BASE_URL", "http://127.0.0.1:8080").rstrip("/")
ORCA_API_KEY = os.getenv("ORCA_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")


def _orca_headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json; charset=utf-8"}
    if ORCA_API_KEY:
        headers["x-api-key"] = ORCA_API_KEY
    return headers


def _orca_request(method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    url = f"{ORCA_BASE_URL}{path}"
    raw = json.dumps(body or {}).encode("utf-8") if body is not None else None
    req = Request(url, data=raw, headers=_orca_headers(), method=method)
    try:
        with urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as err:
        payload = err.read().decode("utf-8", errors="replace") if err.fp else ""
        return {
            "error": {
                "code": "http_error",
                "message": payload or str(err),
                "type": "HTTPError",
                "status": err.code,
            }
        }
    except Exception as exc:
        return {
            "error": {
                "code": "request_failed",
                "message": str(exc),
                "type": exc.__class__.__name__,
            }
        }


def tool_skill_discover(intent: str, limit: int = 5) -> dict[str, Any]:
    return _orca_request(
        "POST",
        "/v1/skills/discover",
        {"intent": intent, "limit": int(limit)},
    )


def tool_skill_describe(skill_id: str) -> dict[str, Any]:
    return _orca_request("GET", f"/v1/skills/{skill_id}/describe")


def tool_skill_execute(skill_id: str, inputs: dict[str, Any], include_trace: bool = False) -> dict[str, Any]:
    return _orca_request(
        "POST",
        f"/v1/skills/{skill_id}/execute",
        {
            "inputs": inputs,
            "include_trace": bool(include_trace),
        },
    )


TOOLS = [
    {
        "type": "function",
        "name": "skill_discover",
        "description": "Discover ORCA skills that match a user intent.",
        "parameters": {
            "type": "object",
            "properties": {
                "intent": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 20},
            },
            "required": ["intent"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "skill_describe",
        "description": "Get full metadata and IO contract for one ORCA skill.",
        "parameters": {
            "type": "object",
            "properties": {
                "skill_id": {"type": "string"},
            },
            "required": ["skill_id"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "skill_execute",
        "description": "Execute one ORCA skill with validated inputs.",
        "parameters": {
            "type": "object",
            "properties": {
                "skill_id": {"type": "string"},
                "inputs": {"type": "object"},
                "include_trace": {"type": "boolean"},
            },
            "required": ["skill_id", "inputs"],
            "additionalProperties": False,
        },
    },
]


def _dispatch_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name == "skill_discover":
        return tool_skill_discover(
            intent=str(arguments.get("intent", "")),
            limit=int(arguments.get("limit", 5)),
        )
    if name == "skill_describe":
        return tool_skill_describe(skill_id=str(arguments.get("skill_id", "")))
    if name == "skill_execute":
        return tool_skill_execute(
            skill_id=str(arguments.get("skill_id", "")),
            inputs=arguments.get("inputs", {}) if isinstance(arguments.get("inputs"), dict) else {},
            include_trace=bool(arguments.get("include_trace", False)),
        )
    return {
        "error": {
            "code": "unknown_tool",
            "message": f"Unsupported tool: {name}",
            "type": "ToolDispatchError",
        }
    }


def run_agent(user_goal: str) -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required")

    client = OpenAI(api_key=api_key)

    system_prompt = (
        "Eres un agente de produccion. Debes usar ORCA como unica capa de ejecucion de negocio. "
        "Proceso obligatorio: (1) skill_discover, (2) skill_describe si hace falta confirmar inputs, "
        "(3) skill_execute para resolver la tarea. "
        "No entregues respuesta final sin ejecutar al menos una skill. "
        "Si no hay skill adecuada, indica que se requiere authoring de una nueva skill en ORCA."
    )

    response = client.responses.create(
        model=OPENAI_MODEL,
        input=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_goal},
        ],
        tools=TOOLS,
    )

    executed_skill = False
    forced_retry_used = False

    for _ in range(10):
        tool_calls = [item for item in response.output if item.type == "function_call"]

        if not tool_calls:
            if executed_skill:
                return response.output_text

            if forced_retry_used:
                return (
                    "No se pudo completar con enforcement ORCA. "
                    "El modelo no ejecuto ninguna skill; reintenta o revisa tools/configuracion."
                )

            forced_retry_used = True
            response = client.responses.create(
                model=OPENAI_MODEL,
                previous_response_id=response.id,
                input=[
                    {
                        "role": "system",
                        "content": (
                            "Debes llamar herramientas ORCA antes de responder. "
                            "Llama skill_discover y despues skill_execute."
                        ),
                    }
                ],
                tools=TOOLS,
            )
            continue

        tool_outputs: list[dict[str, Any]] = []
        for call in tool_calls:
            try:
                args = json.loads(call.arguments) if call.arguments else {}
            except json.JSONDecodeError:
                args = {}

            result = _dispatch_tool(call.name, args)
            if call.name == "skill_execute" and "error" not in result:
                executed_skill = True

            tool_outputs.append(
                {
                    "type": "function_call_output",
                    "call_id": call.call_id,
                    "output": json.dumps(result, ensure_ascii=False),
                }
            )

        response = client.responses.create(
            model=OPENAI_MODEL,
            previous_response_id=response.id,
            input=tool_outputs,
            tools=TOOLS,
        )

    return "Se alcanzo el maximo de iteraciones sin cerrar una respuesta final."


def main() -> int:
    if len(sys.argv) < 2:
        print("Uso: python examples/orca_external_agent.py \"tu objetivo\"")
        return 2

    goal = " ".join(sys.argv[1:]).strip()
    answer = run_agent(goal)
    print(answer)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

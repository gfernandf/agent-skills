"""
Intent -> ORCA skill -> ORCA execution bridge.

This script demonstrates a practical integration pattern:
1) Receive a natural-language instruction.
2) Ask ORCA capability agent.plan.create to generate a skill YAML.
3) Persist the generated skill into local skills.
4) Build an input payload for required skill inputs.
5) Execute the generated skill via ORCA HTTP API.

Environment variables:
  ORCA_BASE_URL    default: http://127.0.0.1:8080
  ORCA_API_KEY     optional x-api-key for protected routes
  HOST_ROOT        default: repository root containing skills/local
  OPENAI_API_KEY   optional; used only to map instruction -> skill inputs
  OPENAI_MODEL     default: gpt-4.1-mini

Usage:
  python examples/orca_intent_skill_bridge.py "send email to all users about maintenance window"
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import yaml


ORCA_BASE_URL = os.getenv("ORCA_BASE_URL", "http://127.0.0.1:8080").rstrip("/")
ORCA_API_KEY = os.getenv("ORCA_API_KEY", "")
HOST_ROOT = Path(os.getenv("HOST_ROOT", str(Path(__file__).resolve().parent.parent)))
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")


def _headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json; charset=utf-8"}
    if ORCA_API_KEY:
        headers["x-api-key"] = ORCA_API_KEY
    return headers


def _http_json(method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    url = f"{ORCA_BASE_URL}{path}"
    payload = json.dumps(body or {}).encode("utf-8") if body is not None else None
    req = Request(url, data=payload, headers=_headers(), method=method)
    try:
        with urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as err:
        txt = err.read().decode("utf-8", errors="replace") if err.fp else str(err)
        return {
            "error": {
                "code": "http_error",
                "status": err.code,
                "message": txt,
                "type": "HTTPError",
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


def _default_for_type(field_type: str, instruction: str) -> Any:
    if field_type == "string":
        return instruction
    if field_type in {"number", "integer"}:
        return 1
    if field_type == "boolean":
        return True
    if field_type == "array":
        return [instruction]
    if field_type == "object":
        return {"instruction": instruction}
    return instruction


def _heuristic_inputs(skill_doc: dict[str, Any], instruction: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    inputs = skill_doc.get("inputs", {})
    if not isinstance(inputs, dict):
        return out

    for name, spec in inputs.items():
        if not isinstance(spec, dict):
            continue
        if not spec.get("required", False):
            continue
        ftype = str(spec.get("type", "string"))
        out[name] = _default_for_type(ftype, instruction)

    return out


def _llm_inputs(skill_doc: dict[str, Any], instruction: str) -> dict[str, Any] | None:
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        return None

    try:
        from openai import OpenAI
    except Exception:
        return None

    client = OpenAI(api_key=api_key)

    raw_inputs = skill_doc.get("inputs", {})
    if not isinstance(raw_inputs, dict):
        raw_inputs = {}

    input_schema = {
        "type": "object",
        "properties": {},
        "required": [],
    }
    for k, v in raw_inputs.items():
        if not isinstance(v, dict):
            continue
        input_schema["properties"][k] = {"type": v.get("type", "string")}
        if v.get("required", False):
            input_schema["required"].append(k)

    prompt = (
        "Map the user instruction to a JSON object matching the required skill inputs. "
        "Return only JSON object with top-level input fields. "
        "Do not include explanations."
    )

    response = client.responses.create(
        model=OPENAI_MODEL,
        input=[
            {
                "role": "system",
                "content": "You build input payloads for ORCA skill execution.",
            },
            {
                "role": "user",
                "content": (
                    f"Instruction: {instruction}\n\n"
                    f"Skill input schema: {json.dumps(input_schema, ensure_ascii=False)}"
                ),
            },
            {"role": "user", "content": prompt},
        ],
    )

    text = (response.output_text or "").strip()
    if not text:
        return None

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def _save_local_skill(skill_id: str, skill_yaml: str) -> Path:
    if "." not in skill_id:
        raise ValueError(f"Invalid skill id: {skill_id}")
    domain, slug = skill_id.split(".", 1)
    out_dir = HOST_ROOT / "skills" / "local" / domain / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    skill_path = out_dir / "skill.yaml"
    skill_path.write_text(skill_yaml, encoding="utf-8")
    return skill_path


def run_bridge(instruction: str) -> int:
    create_result = _http_json(
        "POST",
        "/v1/capabilities/agent.plan.create/execute",
        {
            "inputs": {
                "intent_description": instruction,
                "target_channel": "local",
            }
        },
    )

    if "error" in create_result:
        print("[bridge] ORCA create capability failed")
        print(json.dumps(create_result, ensure_ascii=False, indent=2))
        return 1

    outputs = create_result.get("outputs", {})
    if not isinstance(outputs, dict):
        print("[bridge] Unexpected outputs from agent.plan.create")
        print(json.dumps(create_result, ensure_ascii=False, indent=2))
        return 1

    skill_yaml = outputs.get("skill_yaml", "")
    skill_id = outputs.get("suggested_id", "")
    validation_errors = outputs.get("validation_errors", [])

    if validation_errors:
        print("[bridge] Generated skill has validation errors:")
        print(json.dumps(validation_errors, ensure_ascii=False, indent=2))
        return 1

    if not skill_yaml or not skill_id:
        print("[bridge] Missing skill_yaml or suggested_id")
        print(json.dumps(create_result, ensure_ascii=False, indent=2))
        return 1

    skill_path = _save_local_skill(skill_id, skill_yaml)
    print(f"[bridge] Skill created: {skill_id}")
    print(f"[bridge] Saved at: {skill_path}")

    skill_doc = yaml.safe_load(skill_yaml)
    if not isinstance(skill_doc, dict):
        print("[bridge] Generated YAML is not a valid mapping")
        return 1

    llm_payload = _llm_inputs(skill_doc, instruction)
    inputs_payload = llm_payload if isinstance(llm_payload, dict) else _heuristic_inputs(skill_doc, instruction)

    print("[bridge] Execution inputs:")
    print(json.dumps(inputs_payload, ensure_ascii=False, indent=2))

    exec_result = _http_json(
        "POST",
        f"/v1/skills/{skill_id}/execute",
        {"inputs": inputs_payload, "include_trace": True},
    )

    if "error" in exec_result:
        print("[bridge] Skill execution failed.")
        print(json.dumps(exec_result, ensure_ascii=False, indent=2))
        print(
            "[bridge] If the skill is reported as not found, restart the ORCA HTTP server to reload local skills."
        )
        return 1

    print("[bridge] Skill execution succeeded:")
    print(json.dumps(exec_result, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python examples/orca_intent_skill_bridge.py \"your instruction\"")
        return 2
    instruction = " ".join(sys.argv[1:]).strip()
    return run_bridge(instruction)


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3

from __future__ import annotations

import json
import socket
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


def _request_json(
    req: urllib.request.Request,
    *,
    timeout: float,
    attempts: int = 3,
    retry_delay_seconds: float = 0.5,
) -> dict:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code in {500, 502, 503, 504} and attempt < attempts:
                last_error = exc
                time.sleep(retry_delay_seconds * attempt)
                continue
            raise
        except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
            last_error = exc
            if attempt < attempts:
                time.sleep(retry_delay_seconds * attempt)
                continue
            raise
    raise RuntimeError(f"request failed after retries: {last_error}")


def _http_get_json(url: str, headers: dict[str, str] | None = None) -> dict:
    req = urllib.request.Request(url, headers=headers or {}, method="GET")
    return _request_json(req, timeout=30)


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
    req = urllib.request.Request(url, data=data, headers=request_headers, method="POST")
    return _request_json(req, timeout=45)


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


def _wait_for_server_ready_or_exit(
    proc: subprocess.Popen[bytes],
    base_url: str,
    *,
    timeout_seconds: float = 45.0,
) -> None:
    deadline = time.time() + timeout_seconds
    last_error: Exception | None = None
    while time.time() < deadline:
        code = proc.poll()
        if code is not None:
            raise RuntimeError(
                f"HTTP server exited before ready with code={code} at {base_url}"
            )
        try:
            health = _http_get_json(f"{base_url}/v1/health")
            if isinstance(health, dict) and health.get("status") == "ok":
                return
        except Exception as exc:  # pragma: no cover - exercised in integration runs
            last_error = exc
        time.sleep(0.25)
    raise RuntimeError(f"server did not become ready at {base_url}: {last_error}")


def _pick_skill_candidates(
    base_url: str, *, headers: dict[str, str]
) -> list[tuple[str, dict]]:
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
        (
            "text.language-summary",
            {"text": "Build a safe runtime execution plan."},
        ),
        (
            "text.quick-summary",
            {"text": "Build a safe runtime execution plan."},
        ),
        (
            "agent.plan-and-route",
            {"objective": "Build a safe runtime execution plan."},
        ),
        (
            "agent.execute-from-plan",
            {"objective": "Build a safe runtime execution plan."},
        ),
        (
            "agent.orchestrate-from-prompt",
            {"objective": "Build a safe runtime execution plan."},
        ),
    ]
    candidates = [
        (skill_id, payload) for skill_id, payload in preferred if skill_id in available
    ]
    # Last-resort fallback: try any listed skill with a generic text payload.
    for skill_id in sorted(available):
        if skill_id not in {candidate[0] for candidate in candidates}:
            candidates.append(
                (skill_id, {"text": "Build a safe runtime execution plan."})
            )
    if not candidates:
        raise RuntimeError(f"none of preferred verification skills found: {preferred}")
    return candidates


def _infer_inputs_from_description(desc: dict, default_payload: dict) -> dict:
    inputs_schema = desc.get("inputs") if isinstance(desc, dict) else None
    if not isinstance(inputs_schema, dict):
        return default_payload

    inferred: dict[str, object] = {}
    for field_name, field_spec in inputs_schema.items():
        if not isinstance(field_name, str):
            continue
        field_type = None
        required = False
        if isinstance(field_spec, dict):
            maybe_type = field_spec.get("type")
            if isinstance(maybe_type, str):
                field_type = maybe_type.lower()
            required = bool(field_spec.get("required", False))

        # Keep known defaults when the field exists in schema.
        if field_name in default_payload:
            inferred[field_name] = default_payload[field_name]
            continue

        if field_name in {"text", "content", "objective", "query", "prompt", "input"}:
            inferred[field_name] = "Build a safe runtime execution plan."
            continue

        if required:
            if field_type in {"boolean", "bool"}:
                inferred[field_name] = True
            elif field_type in {"integer", "int"}:
                inferred[field_name] = 1
            elif field_type in {"number", "float"}:
                inferred[field_name] = 1.0
            elif field_type in {"array", "list"}:
                inferred[field_name] = []
            elif field_type in {"object", "map", "dict"}:
                inferred[field_name] = {}
            else:
                inferred[field_name] = "sample"

    return inferred or default_payload


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
        _wait_for_server_ready_or_exit(http_proc, base_url)
        candidates = _pick_skill_candidates(base_url, headers=headers)

        health = _http_get_json(f"{base_url}/v1/health")
        if health.get("status") != "ok":
            raise RuntimeError("health endpoint did not return status=ok")

        selected_skill_id: str | None = None
        selected_skill_inputs: dict | None = None
        exec_result: dict | None = None
        last_error: str | None = None

        for skill_id, skill_inputs in candidates:
            desc = _http_get_json(
                f"{base_url}/v1/skills/{skill_id}/describe",
                headers=headers,
            )
            if desc.get("id") != skill_id:
                last_error = f"describe mismatch for {skill_id}"
                continue

            effective_inputs = _infer_inputs_from_description(desc, skill_inputs)

            candidate_result = _http_post_json(
                f"{base_url}/v1/skills/{skill_id}/execute",
                {
                    "inputs": effective_inputs,
                    "include_trace": False,
                },
                headers=headers,
            )
            if "outputs" in candidate_result:
                selected_skill_id = skill_id
                selected_skill_inputs = effective_inputs
                exec_result = candidate_result
                break

            status = candidate_result.get("status", "unknown")
            last_error = f"{skill_id} returned status={status} without outputs"

        if (
            selected_skill_id is None
            or selected_skill_inputs is None
            or exec_result is None
        ):
            raise RuntimeError(
                f"execute endpoint did not return outputs for any candidate: {last_error}"
            )

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
                "skill_id": selected_skill_id,
                "inputs": selected_skill_inputs,
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

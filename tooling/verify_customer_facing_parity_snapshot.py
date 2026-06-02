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
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
REGISTRY_ROOT = ROOT.parent / "agent-skill-registry"
SNAPSHOT_PATH = ROOT / "tooling" / "snapshots" / "consumer_facing_parity_v1.json"

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
) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            # Only retry transient server-side failures.
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


def _http_get_json(url: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
    req = urllib.request.Request(url, headers=headers or {}, method="GET")
    return _request_json(req, timeout=45)


def _http_post_json(
    url: str, payload: dict[str, Any], headers: dict[str, str] | None = None
) -> dict[str, Any]:
    req_headers = {"Content-Type": "application/json"}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=req_headers,
        method="POST",
    )
    return _request_json(req, timeout=75)


def _wait_for_server_ready(
    base_url: str,
    *,
    headers: dict[str, str],
    timeout_seconds: float = 20.0,
) -> None:
    deadline = time.time() + timeout_seconds
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            health = _http_get_json(f"{base_url}/v1/health")
            if isinstance(health, dict) and health.get("status") == "ok":
                _http_get_json(f"{base_url}/v1/skills/list", headers=headers)
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


def _pick_skill_candidates(base_url: str, *, headers: dict[str, str]) -> list[str]:
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
        "text.language-summary",
        "text.quick-summary",
        "agent.plan-and-route",
        "agent.execute-from-plan",
        "agent.orchestrate-from-prompt",
    ]
    candidates = [skill_id for skill_id in preferred if skill_id in available]
    for skill_id in sorted(available):
        if skill_id not in candidates:
            candidates.append(skill_id)
    if not candidates:
        raise RuntimeError("no skills were returned by /v1/skills/list")
    return candidates


def _infer_inputs_from_description(
    desc: dict[str, Any], default_text: str
) -> dict[str, Any]:
    inputs_schema = desc.get("inputs") if isinstance(desc, dict) else None
    if not isinstance(inputs_schema, dict):
        return {"text": default_text}

    inferred: dict[str, Any] = {}
    for field_name, field_spec in inputs_schema.items():
        if not isinstance(field_name, str):
            continue

        field_type = ""
        required = False
        if isinstance(field_spec, dict):
            maybe_type = field_spec.get("type")
            if isinstance(maybe_type, str):
                field_type = maybe_type.lower()
            required = bool(field_spec.get("required", False))

        if field_name in {"text", "content", "objective", "query", "prompt", "input"}:
            inferred[field_name] = default_text
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

    return inferred or {"text": default_text}


def _normalize(value: Any) -> Any:
    if isinstance(value, dict):
        # Ignore volatile observability/enrichment fields that are not part of parity contract semantics.
        ignored_keys = {
            "trace_id",
            "timestamp",
            "runtime_root",
            "registry_root",
            "host_root",
            "duration_ms",
            "resolution_ms",
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
    base_url = "http://127.0.0.1:8086"
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
    candidates = _pick_skill_candidates(base_url, headers=headers)

    http_health = _http_get_json(f"{base_url}/v1/health")
    mcp_health = bridge.call_tool("runtime.health", {})

    selected_skill_id: str | None = None
    http_desc: dict[str, Any] | None = None
    mcp_desc: dict[str, Any] | None = None
    http_skill_exec: dict[str, Any] | None = None
    mcp_skill_exec: dict[str, Any] | None = None

    for candidate_skill_id in candidates:
        candidate_http_desc = _http_get_json(
            f"{base_url}/v1/skills/{candidate_skill_id}/describe", headers=headers
        )
        if candidate_http_desc.get("id") != candidate_skill_id:
            continue

        candidate_inputs = _infer_inputs_from_description(
            candidate_http_desc,
            "Build a policy-compliant execution plan.",
        )
        candidate_http_exec = _http_post_json(
            f"{base_url}/v1/skills/{candidate_skill_id}/execute",
            {"inputs": candidate_inputs, "include_trace": False},
            headers=headers,
        )
        candidate_mcp_desc = bridge.call_tool(
            "skill.describe", {"skill_id": candidate_skill_id}
        )
        candidate_mcp_exec = bridge.call_tool(
            "skill.execute",
            {
                "skill_id": candidate_skill_id,
                "inputs": candidate_inputs,
                "include_trace": False,
            },
        )

        if "outputs" in candidate_http_exec and "outputs" in candidate_mcp_exec:
            selected_skill_id = candidate_skill_id
            http_desc = candidate_http_desc
            mcp_desc = candidate_mcp_desc
            http_skill_exec = candidate_http_exec
            mcp_skill_exec = candidate_mcp_exec
            break

    if (
        selected_skill_id is None
        or http_desc is None
        or mcp_desc is None
        or http_skill_exec is None
        or mcp_skill_exec is None
    ):
        raise RuntimeError("no executable skill found for parity snapshot")

    capability_inputs = {
        "payload": {"title": "Hello"},
        "constraint": {"required_keys": ["title"], "forbidden_keys": ["password"]},
    }
    http_cap_exec = _http_post_json(
        f"{base_url}/v1/capabilities/policy.constraint.validate/execute",
        {"inputs": capability_inputs},
        headers=headers,
    )
    mcp_cap_exec = bridge.call_tool(
        "capability.execute",
        {"capability_id": "policy.constraint.validate", "inputs": capability_inputs},
    )

    snapshot = {
        "skill_id": selected_skill_id,
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

    snapshot["all_equal"] = all(
        section.get("equal")
        for section in snapshot.values()
        if isinstance(section, dict) and "equal" in section
    )
    return snapshot


def _stable_projection(snapshot: dict[str, Any]) -> dict[str, Any]:
    def _summary(payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return {"type": type(payload).__name__}

        outputs = (
            payload.get("outputs") if isinstance(payload.get("outputs"), dict) else {}
        )
        meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
        return {
            "status": payload.get("status"),
            "top_level_keys": sorted(payload.keys()),
            "output_keys": sorted(outputs.keys())
            if isinstance(payload.get("capability_id"), str)
            else [],
            "meta_keys": sorted(meta.keys())
            if isinstance(payload.get("capability_id"), str)
            else [],
        }

    projected: dict[str, Any] = {
        "skill_id": snapshot.get("skill_id"),
        "all_equal": snapshot.get("all_equal"),
    }

    for section in ("health", "describe_skill", "execute_skill", "execute_capability"):
        value = snapshot.get(section)
        if not isinstance(value, dict):
            continue
        projected[section] = {
            "equal": value.get("equal"),
            "http": _summary(value.get("http")),
            "mcp": _summary(value.get("mcp")),
        }
    return projected


def main() -> int:
    api_key = "parity-key"
    base_url = "http://127.0.0.1:8086"
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
        _wait_for_server_ready(base_url, headers={"x-api-key": api_key})
        actual = _stable_projection(_compute_snapshot(api_key))

        if not actual.get("all_equal"):
            raise RuntimeError(
                "HTTP and MCP outputs diverge for at least one operation."
            )

        if SNAPSHOT_PATH.exists():
            expected = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
            if actual != expected:
                diff_path = SNAPSHOT_PATH.with_suffix(".actual.json")
                diff_path.write_text(
                    json.dumps(actual, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                )
                raise RuntimeError(
                    "Parity snapshot mismatch. "
                    f"Expected snapshot in {SNAPSHOT_PATH.name}; actual written to {diff_path.name}."
                )
        else:
            SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
            SNAPSHOT_PATH.write_text(
                json.dumps(actual, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

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

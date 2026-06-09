#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REGISTRY_ROOT = ROOT.parent / "agent-skill-registry"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from customer_facing.neutral_api import NeutralRuntimeAPI
from official_mcp_servers import governance_tools


def _safe_id(capability_id: str) -> str:
    return capability_id.replace(".", "_")


def _binding_id(capability_id: str) -> str:
    return f"mcp_{_safe_id(capability_id)}_inprocess"


def _write_active_bindings(host_root: Path, capability_ids: list[str]) -> None:
    state_dir = host_root / ".agent-skills"
    state_dir.mkdir(parents=True, exist_ok=True)
    payload = {cap_id: _binding_id(cap_id) for cap_id in capability_ids}
    (state_dir / "active_bindings.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _test_inputs() -> dict[str, dict]:
    return {
        "identity.assignee.identify": {
            "task": {"required_skills": ["python", "ml"]},
            "candidates": [{"id": "alice", "skills": ["python"], "workload": 2}],
        },
        "identity.decision.justify": {
            "decision": "allow",
            "subject": {"id": "alice"},
            "policies": [{"id": "policy-a", "description": "allow read"}],
        },
        "identity.permission.evaluate": {
            "principal": {"id": "alice", "roles": ["admin"]},
            "action": {"type": "read"},
            "resource": {"type": "resource", "id": "r-1"},
            "context": {"elevated_risk": False},
            "policy_refs": ["policy-a"],
        },
        "identity.permission.gate": {
            "principal_id": "alice",
            "permission": "resource:read",
            "context": {"channel": "internal"},
        },
        "identity.permission.get": {"permission_id": "resource:read"},
        "identity.permission.list": {
            "principal_id": "alice",
            "resource_filter": "resource",
        },
        "identity.permission.verify": {
            "principal_id": "alice",
            "permission": "resource:read",
        },
        "identity.risk.score": {
            "principal_id": "alice",
            "signals": {"login_failures": 4, "unusual_hours": True},
        },
        "identity.role.assign": {"principal_id": "bob", "role_id": "viewer"},
        "identity.role.get": {"role_id": "admin"},
        "identity.role.list": {"scope": "admin"},
        "policy.constraint.gate": {
            "payload": {"risk_score": 0.7},
            "gate": {"max_risk": 0.8, "required_fields": ["risk_score"]},
        },
        "policy.constraint.validate": {
            "payload": {"department": "finance"},
            "constraint": {"required_fields": ["department"]},
        },
        "policy.decision.evaluate": {
            "decision_context": {
                "principal": {"id": "alice"},
                "action": {"type": "export"},
                "resource": {"classification": "sensitive"},
            },
            "violations": [{"severity": "high", "rule": "export-control"}],
            "risk": {"score": 0.82},
        },
        "policy.decision.justify": {
            "decision": "deny",
            "rules": [{"id": "rule-1", "description": "high-risk deny"}],
            "context": {"channel": "api"},
        },
        "policy.record.classify": {
            "record": {
                "id": "rec-1",
                "type": "ticket",
                "labels": ["security"],
                "fields": {"destination": "vault"},
            },
            "context": {"tenant": "acme"},
        },
        "policy.risk.classify": {
            "action": {"type": "delete", "resource": "customer-data"},
            "categories": ["operational", "compliance"],
        },
        "policy.risk.score": {
            "action": {"type": "delete", "resource": "customer-data"},
            "dimensions": ["impact", "likelihood"],
        },
        "provenance.citation.generate": {
            "source": {"url": "https://example.com", "title": "Example", "id": "src-1"},
            "excerpt": "governance evidence",
            "locator": "section-1",
        },
        "provenance.decision.store": {
            "decision_id": "dec-001",
            "principal": {"id": "alice"},
            "action": {"type": "release_output"},
            "resource": {"id": "doc-1"},
            "decision": {"outcome": "deny", "rationale": "policy block"},
            "policy_refs": ["policy-1"],
            "evidence": {"rule": "policy-1"},
        },
        "provenance.trace.summarize": {
            "execution_trace": {
                "trace_ref": "run-001",
                "status": "success",
                "step_results": [
                    {"step_id": "s1", "status": "success"},
                    {"step_id": "s2", "status": "success"},
                ],
            }
        },
        "security.content.classify": {
            "payload": {"text": "api key and payment card appear in this text"},
            "context": {"channel": "ticket"},
        },
        "security.output.gate": {
            "output": {"text": "safe response", "risk_score": 0.2},
            "policy": {"max_risk": 0.4},
        },
        "security.pii.detect": {"text": "Contact me at alice@example.com"},
        "security.pii.redact": {"text": "Contact me at alice@example.com"},
        "security.secret.detect": {"text": "token=abc123 and secret=xyz"},
    }


def _assert_meta(meta: dict, capability_id: str) -> None:
    expected_binding = _binding_id(capability_id)
    expected_service = "governance_mcp_inprocess"

    if meta.get("binding_id") != expected_binding:
        raise RuntimeError(
            f"{capability_id}: expected binding_id {expected_binding!r}, got {meta.get('binding_id')!r}"
        )

    if meta.get("service_id") != expected_service:
        raise RuntimeError(
            f"{capability_id}: expected service_id {expected_service!r}, got {meta.get('service_id')!r}"
        )


def _assert_outputs(capability_id: str, inputs: dict, outputs: dict) -> None:
    if capability_id == "provenance.decision.store":
        if not isinstance(outputs, dict):
            raise RuntimeError(f"{capability_id}: outputs must be an object")
        if outputs.get("recorded") is not True:
            raise RuntimeError(
                f"{capability_id}: expected recorded=True, got {outputs!r}"
            )
        if not isinstance(outputs.get("record_id"), str) or not outputs.get(
            "record_id"
        ):
            raise RuntimeError(f"{capability_id}: invalid record_id in {outputs!r}")
        if not isinstance(outputs.get("timestamp"), str) or not outputs.get(
            "timestamp"
        ):
            raise RuntimeError(f"{capability_id}: invalid timestamp in {outputs!r}")
        if "rationale" not in outputs:
            raise RuntimeError(f"{capability_id}: missing rationale in {outputs!r}")
        return

    expected = governance_tools.call_tool(capability_id, dict(inputs))
    if not isinstance(outputs, dict):
        raise RuntimeError(f"{capability_id}: outputs must be an object")

    mismatches = []
    for key, expected_value in expected.items():
        actual_value = outputs.get(key)
        if actual_value != expected_value:
            mismatches.append((key, expected_value, actual_value))

    if mismatches:
        raise RuntimeError(
            f"{capability_id}: MCP output mismatch for expected keys: {mismatches!r}; actual={outputs!r}"
        )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify governance MCP in-process routing across full governance capability slice."
    )
    parser.add_argument(
        "--registry-root",
        type=Path,
        default=DEFAULT_REGISTRY_ROOT,
        help="Path to agent-skill-registry root.",
    )
    parser.add_argument(
        "--runtime-root",
        type=Path,
        default=ROOT,
        help="Path to agent-skills runtime root.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    inputs_by_capability = _test_inputs()
    capability_ids = sorted(inputs_by_capability.keys())

    with tempfile.TemporaryDirectory(prefix="agent-skills-mcp-governance-") as tmpdir:
        host_root = Path(tmpdir)
        _write_active_bindings(host_root, capability_ids)

        api = NeutralRuntimeAPI(
            registry_root=args.registry_root,
            runtime_root=args.runtime_root,
            host_root=host_root,
        )

        for capability_id in capability_ids:
            result = api.execute_capability(
                capability_id, inputs_by_capability[capability_id]
            )
            outputs = result.get("outputs") if isinstance(result, dict) else None
            meta = result.get("meta", {}) if isinstance(result, dict) else {}

            _assert_meta(meta, capability_id)
            _assert_outputs(capability_id, inputs_by_capability[capability_id], outputs)

    print("MCP governance slice verification passed.")
    print(f"capabilities_verified={len(capability_ids)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

from typing import Any

from official_services import identity_baseline, policy_baseline, provenance_baseline
from official_services import security_baseline


_SUPPORTED_TOOLS = {
    "identity.assignee.identify": identity_baseline.identify_assignee,
    "identity.decision.justify": identity_baseline.justify_decision,
    "identity.permission.gate": identity_baseline.gate_permission,
    "identity.permission.get": identity_baseline.get_permission,
    "identity.permission.list": identity_baseline.list_permissions,
    "identity.permission.verify": identity_baseline.verify_permission,
    "identity.risk.score": identity_baseline.score_risk,
    "identity.role.assign": identity_baseline.assign_role,
    "identity.role.get": identity_baseline.get_role,
    "identity.role.list": identity_baseline.list_roles,
    "policy.constraint.gate": policy_baseline.gate_constraint,
    "policy.constraint.validate": policy_baseline.validate_constraint,
    "policy.decision.evaluate": policy_baseline.evaluate_decision,
    "policy.decision.justify": policy_baseline.justify_decision,
    "policy.record.classify": policy_baseline.classify_record,
    "policy.risk.classify": policy_baseline.classify_risk,
    "policy.risk.score": policy_baseline.score_risk,
    "evidence.citation.generate": provenance_baseline.generate_governance_citation,
    "evidence.trace.summarize": provenance_baseline.summarize_trace,
    "security.output.gate": security_baseline.gate_output,
    "security.pii.detect": security_baseline.detect_pii,
    "security.pii.redact": security_baseline.redact_pii,
    "security.secret.detect": security_baseline.detect_secret,
}


def call_tool(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(tool_name, str) or not tool_name:
        raise ValueError("tool_name must be a non-empty string")

    if not isinstance(arguments, dict):
        raise ValueError("arguments must be a mapping")

    tool = _SUPPORTED_TOOLS.get(tool_name)
    if tool is None:
        raise ValueError(f"Unsupported MCP tool '{tool_name}'.")

    result = tool(**arguments)
    if not isinstance(result, dict):
        raise TypeError(f"MCP tool '{tool_name}' returned a non-mapping result.")

    return result

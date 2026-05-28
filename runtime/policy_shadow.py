from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable
from urllib import error as urllib_error
from urllib import request as urllib_request


_TRUST_LEVEL_RANK: dict[str, int] = {
    "sandbox": 0,
    "standard": 1,
    "elevated": 2,
    "privileged": 3,
}


@dataclass(frozen=True)
class PolicyDecisionInput:
    capability_id: str
    step_id: str
    safety: dict[str, Any]
    context_trust_level: str
    confirmed_capabilities: list[str]
    context_tenant_id: str | None = None
    target_tenant_id: str | None = None


@dataclass(frozen=True)
class PolicyDecision:
    status: str
    reason: str | None = None


@runtime_checkable
class ExternalPolicyAdapter(Protocol):
    def decide_pre(self, payload: PolicyDecisionInput) -> PolicyDecision: ...


def evaluate_internal_pre(payload: PolicyDecisionInput) -> PolicyDecision:
    safety = payload.safety or {}

    required_trust = safety.get("trust_level")
    if isinstance(required_trust, str):
        required_rank = _TRUST_LEVEL_RANK.get(required_trust, 1)
        context_rank = _TRUST_LEVEL_RANK.get(payload.context_trust_level, 1)
        if context_rank < required_rank:
            return PolicyDecision(
                status="block",
                reason=(
                    f"trust_level_insufficient:{payload.context_trust_level}<"
                    f"{required_trust}"
                ),
            )

    if safety.get("requires_confirmation") is True:
        if payload.capability_id not in payload.confirmed_capabilities:
            return PolicyDecision(status="require_human", reason="confirmation_required")

    allowed_targets = safety.get("allowed_targets")
    if isinstance(allowed_targets, list) and "same_tenant" in allowed_targets:
        context_tenant = (
            payload.context_tenant_id.strip()
            if isinstance(payload.context_tenant_id, str)
            else ""
        )
        if not context_tenant:
            return PolicyDecision(status="block", reason="same_tenant_context_missing")

        if isinstance(payload.target_tenant_id, str) and payload.target_tenant_id.strip():
            target_tenant = payload.target_tenant_id.strip()
            if target_tenant != context_tenant:
                return PolicyDecision(
                    status="block",
                    reason=(
                        "same_tenant_mismatch:"
                        f"{target_tenant}!={context_tenant}"
                    ),
                )

    # Gate decisions are handled by runtime gate execution and are not part of this
    # initial shadow parity baseline.
    return PolicyDecision(status="allow")


class MirrorExternalPolicyAdapter:
    """Reference adapter that mirrors current internal baseline semantics.

    This adapter is intentionally deterministic and local-only so policy shadow mode
    can be validated without external services.
    """

    def decide_pre(self, payload: PolicyDecisionInput) -> PolicyDecision:
        return evaluate_internal_pre(payload)


class OpaHttpPolicyAdapter:
    """Optional OPA-compatible HTTP adapter for policy pre-decisions.

    Expected endpoint behavior:
    - Accepts POST JSON payload with shape: {"input": {...PolicyDecisionInput...}}
    - Returns JSON with shape:
      1) {"result": true|false}
      2) {"result": {"status": "allow|block|require_human", "reason": "..."}}
      3) {"result": {"allow": true|false, "reason": "..."}}
    """

    def __init__(self, url: str, *, timeout_seconds: float = 2.0) -> None:
        self.url = url
        self.timeout_seconds = timeout_seconds

    def decide_pre(self, payload: PolicyDecisionInput) -> PolicyDecision:
        body = {
            "input": {
                "capability_id": payload.capability_id,
                "step_id": payload.step_id,
                "safety": payload.safety,
                "context_trust_level": payload.context_trust_level,
                "confirmed_capabilities": list(payload.confirmed_capabilities),
                "context_tenant_id": payload.context_tenant_id,
                "target_tenant_id": payload.target_tenant_id,
            }
        }

        req = urllib_request.Request(
            self.url,
            method="POST",
            data=json.dumps(body, ensure_ascii=True).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )

        try:
            with urllib_request.urlopen(req, timeout=self.timeout_seconds) as resp:
                raw = resp.read().decode("utf-8")
        except urllib_error.URLError as exc:
            raise RuntimeError(f"OPA request failed: {exc}") from exc

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError("OPA response is not valid JSON") from exc

        result = parsed.get("result") if isinstance(parsed, dict) else None
        if isinstance(result, bool):
            return PolicyDecision(status="allow" if result else "block", reason=None)

        if isinstance(result, dict):
            status = result.get("status")
            reason = result.get("reason")
            if isinstance(status, str) and status in {"allow", "block", "require_human"}:
                return PolicyDecision(status=status, reason=reason if isinstance(reason, str) else None)
            allow = result.get("allow")
            if isinstance(allow, bool):
                return PolicyDecision(
                    status="allow" if allow else "block",
                    reason=reason if isinstance(reason, str) else None,
                )

        raise RuntimeError("OPA response missing supported decision fields")


def build_external_policy_adapter_from_env() -> ExternalPolicyAdapter | None:
    adapter_name = os.environ.get("AGENT_SKILLS_POLICY_EXTERNAL_ADAPTER", "").strip().lower()
    if not adapter_name or adapter_name == "none":
        return None
    if adapter_name == "mirror":
        return MirrorExternalPolicyAdapter()
    if adapter_name == "opa":
        url = os.environ.get(
            "AGENT_SKILLS_POLICY_OPA_URL",
            "http://127.0.0.1:8181/v1/data/orca/policy/pre",
        ).strip()
        timeout_raw = os.environ.get("AGENT_SKILLS_POLICY_OPA_TIMEOUT_SECONDS", "2.0")
        try:
            timeout_seconds = float(timeout_raw)
        except ValueError:
            timeout_seconds = 2.0
        return OpaHttpPolicyAdapter(url, timeout_seconds=timeout_seconds)
    raise RuntimeError(
        "Unsupported AGENT_SKILLS_POLICY_EXTERNAL_ADAPTER value: "
        f"'{adapter_name}'. Expected one of: none, mirror, opa."
    )


def compare_decisions(
    payload: PolicyDecisionInput,
    adapter: ExternalPolicyAdapter,
) -> dict[str, Any]:
    internal = evaluate_internal_pre(payload)
    external = adapter.decide_pre(payload)
    equal = (internal.status == external.status) and (internal.reason == external.reason)
    return {
        "input": {
            "capability_id": payload.capability_id,
            "step_id": payload.step_id,
            "context_trust_level": payload.context_trust_level,
            "confirmed_capabilities": list(payload.confirmed_capabilities),
            "context_tenant_id": payload.context_tenant_id,
            "target_tenant_id": payload.target_tenant_id,
            "safety": payload.safety,
        },
        "internal": {
            "status": internal.status,
            "reason": internal.reason,
        },
        "external": {
            "status": external.status,
            "reason": external.reason,
        },
        "equal": equal,
    }

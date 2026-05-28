from __future__ import annotations

from runtime.policy_shadow import (
    OpaHttpPolicyAdapter,
    PolicyDecisionInput,
    build_external_policy_adapter_from_env,
    evaluate_internal_pre,
)


def _payload() -> PolicyDecisionInput:
    return PolicyDecisionInput(
        capability_id="test.cap",
        step_id="s1",
        safety={"trust_level": "standard"},
        context_trust_level="elevated",
        confirmed_capabilities=[],
    )


def test_opa_adapter_parses_boolean_result(monkeypatch):
    adapter = OpaHttpPolicyAdapter("http://fake")

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'{"result": true}'

    monkeypatch.setattr("runtime.policy_shadow.urllib_request.urlopen", lambda *args, **kwargs: _Resp())

    decision = adapter.decide_pre(_payload())
    assert decision.status == "allow"


def test_opa_adapter_parses_status_dict(monkeypatch):
    adapter = OpaHttpPolicyAdapter("http://fake")

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'{"result": {"status": "require_human", "reason": "manual"}}'

    monkeypatch.setattr("runtime.policy_shadow.urllib_request.urlopen", lambda *args, **kwargs: _Resp())

    decision = adapter.decide_pre(_payload())
    assert decision.status == "require_human"
    assert decision.reason == "manual"


def test_build_adapter_from_env_opa(monkeypatch):
    monkeypatch.setenv("AGENT_SKILLS_POLICY_EXTERNAL_ADAPTER", "opa")
    monkeypatch.setenv("AGENT_SKILLS_POLICY_OPA_URL", "http://example/policy")
    adapter = build_external_policy_adapter_from_env()
    assert isinstance(adapter, OpaHttpPolicyAdapter)
    assert adapter.url == "http://example/policy"


def test_build_adapter_from_env_none(monkeypatch):
    monkeypatch.delenv("AGENT_SKILLS_POLICY_EXTERNAL_ADAPTER", raising=False)
    adapter = build_external_policy_adapter_from_env()
    assert adapter is None


def test_same_tenant_requires_context_in_internal_policy():
    payload = PolicyDecisionInput(
        capability_id="decision.task.delegate",
        step_id="s1",
        safety={"allowed_targets": ["same_tenant"]},
        context_trust_level="elevated",
        confirmed_capabilities=[],
        target_tenant_id="tenant-acme",
    )
    decision = evaluate_internal_pre(payload)
    assert decision.status == "block"
    assert decision.reason == "same_tenant_context_missing"


def test_same_tenant_mismatch_blocks_internal_policy():
    payload = PolicyDecisionInput(
        capability_id="decision.task.delegate",
        step_id="s1",
        safety={"allowed_targets": ["same_tenant"]},
        context_trust_level="elevated",
        confirmed_capabilities=[],
        context_tenant_id="tenant-acme",
        target_tenant_id="tenant-beta",
    )
    decision = evaluate_internal_pre(payload)
    assert decision.status == "block"
    assert decision.reason == "same_tenant_mismatch:tenant-beta!=tenant-acme"

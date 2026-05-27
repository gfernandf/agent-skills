from __future__ import annotations

from types import SimpleNamespace

from tooling.audit_openapi_runtime_guardrails import _evaluate_binding
from tooling.audit_openapi_runtime_guardrails import _profile_for_capability


def _binding(
    capability_id: str,
    *,
    timeout_seconds=None,
    retry_count=None,
    fallback_binding_id="python_fallback",
):
    metadata = {}
    if timeout_seconds is not None:
        metadata["timeout_seconds"] = timeout_seconds
    if retry_count is not None:
        metadata["retry_count"] = retry_count
    if fallback_binding_id is not None:
        metadata["fallback_binding_id"] = fallback_binding_id
    return SimpleNamespace(
        id=f"openapi_{capability_id.replace('.', '_')}",
        capability_id=capability_id,
        service_id="model_openai_chat",
        metadata=metadata,
        source_file="bindings/official/example.yaml",
    )


def _service():
    return SimpleNamespace(id="model_openai_chat", base_url="https://api.openai.com/v1")


def test_profile_classification_critical_vs_standard():
    assert _profile_for_capability("decision.option.justify") == "critical"
    assert _profile_for_capability("text.language.detect") == "standard"


def test_critical_binding_short_timeout_is_high_risk():
    entry = _evaluate_binding(
        _binding("decision.option.justify", timeout_seconds=20, retry_count=0),
        _service(),
    )

    ids = {finding["id"] for finding in entry["findings"]}
    assert "timeout_too_low" in ids
    assert any(
        finding["severity"] == "high" and finding["id"] == "timeout_too_low"
        for finding in entry["findings"]
    )
    assert entry["proposed"]["timeout_seconds"] == 45


def test_retry_one_is_allowed():
    entry = _evaluate_binding(
        _binding("text.keyword.extract", timeout_seconds=30, retry_count=1),
        _service(),
    )

    ids = {finding["id"] for finding in entry["findings"]}
    assert "retry_too_high" not in ids


def test_retry_above_one_is_flagged():
    entry = _evaluate_binding(
        _binding("text.keyword.extract", timeout_seconds=30, retry_count=2),
        _service(),
    )

    ids = {finding["id"] for finding in entry["findings"]}
    assert "retry_too_high" in ids


def test_missing_timeout_is_high_risk():
    entry = _evaluate_binding(
        _binding("eval.output.score", timeout_seconds=None, retry_count=0),
        _service(),
    )

    ids = {finding["id"] for finding in entry["findings"]}
    assert "missing_timeout" in ids
    assert any(
        finding["severity"] == "high" and finding["id"] == "missing_timeout"
        for finding in entry["findings"]
    )

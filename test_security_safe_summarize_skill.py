from __future__ import annotations

from pathlib import Path

from cli.main import _build_engine
from runtime.models import ExecutionRequest

import official_services.text_baseline as text_baseline


TEST_ROOT = Path(__file__).resolve().parent
RUNTIME_ROOT = TEST_ROOT
REGISTRY_ROOT = RUNTIME_ROOT.parent / "agent-skill-registry"


def _build_test_engine():
    return _build_engine(REGISTRY_ROOT, RUNTIME_ROOT, RUNTIME_ROOT, None)


def test_safe_summarize_blocks_when_gate_denies(monkeypatch):
    def leaky_summary(text, max_length=None):  # noqa: ARG001
        return {"summary": "Contact me at leaked@example.com", "_fallback": True}

    monkeypatch.setattr(text_baseline, "summarize_text", leaky_summary)

    engine = _build_test_engine()
    req = ExecutionRequest(
        skill_id="security.safe-summarize",
        inputs={
            "text": "John Doe (john.doe@acme.com) asked for account help.",
            "block_pii": True,
            "max_length": 120,
        },
        trace_id="test-safe-summarize-blocked",
        channel="test",
    )

    result = engine.execute(req)

    assert result.status == "completed"
    assert result.outputs["pii_detected"] is True
    assert result.outputs["gate_allowed"] is False
    assert result.outputs["summary"] == "[BLOCKED: output contained sensitive data]"


def test_safe_summarize_allows_clean_summary(monkeypatch):
    def clean_summary(text, max_length=None):  # noqa: ARG001
        return {
            "summary": "Customer reported duplicate billing charge and requested review.",
            "_fallback": True,
        }

    monkeypatch.setattr(text_baseline, "summarize_text", clean_summary)

    engine = _build_test_engine()
    req = ExecutionRequest(
        skill_id="security.safe-summarize",
        inputs={
            "text": "John Doe (john.doe@acme.com) reported duplicate billing.",
            "block_pii": True,
            "max_length": 120,
        },
        trace_id="test-safe-summarize-allowed",
        channel="test",
    )

    result = engine.execute(req)

    assert result.status == "completed"
    assert result.outputs["pii_detected"] is True
    assert result.outputs["gate_allowed"] is True
    assert (
        result.outputs["summary"]
        == "Customer reported duplicate billing charge and requested review."
    )

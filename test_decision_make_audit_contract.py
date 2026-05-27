"""Audit contract tests for decision.make skill execution.

Goal: ensure any matching decision prompt gets a stable, well-structured
meta diagnostics block for downstream auditing.
"""

from __future__ import annotations

import pytest

from sdk.embedded import execute_with_meta, reset


@pytest.fixture(autouse=True)
def _deterministic_runtime(monkeypatch):
    """Force local deterministic execution path for tests."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    reset()
    yield
    reset()


@pytest.mark.parametrize(
    "inputs",
    [
        {
            "goal": "Debemos lanzar un nuevo SaaS para equipos legales en Espana en 12 meses?",
            "context_items": [
                {
                    "id": "ctx-1",
                    "content": "Presupuesto 600000 EUR, equipo 5 personas, sin experiencia legaltech.",
                },
                {
                    "id": "ctx-2",
                    "content": "Opciones: construir completo, MVP, posponer. Competencia establecida.",
                },
            ],
            "options": [
                {
                    "id": "full",
                    "label": "construir producto completo",
                    "description": "Build full product",
                },
                {
                    "id": "mvp",
                    "label": "lanzar piloto/MVP",
                    "description": "Pilot first",
                },
                {"id": "wait", "label": "posponer", "description": "Delay decision"},
            ],
            "option_constraint_mode": "strict",
            "risk_tolerance": "medium",
        },
        {
            "goal": "Should we enter legaltech Spain in the next 12 months with limited team capacity?",
            "context_items": [
                {
                    "id": "ctx-a",
                    "content": "B2B SaaS experience yes, legaltech experience no, incumbents exist.",
                }
            ],
            "risk_tolerance": "low",
        },
    ],
)
def test_decision_make_meta_contract(inputs):
    result = execute_with_meta("decision.make", inputs)

    assert isinstance(result, dict)
    assert "outputs" in result
    assert "meta" in result

    outputs = result["outputs"]
    meta = result["meta"]

    # Output sanity for decision flows
    assert isinstance(outputs.get("recommendation"), str)
    assert isinstance(outputs.get("alternatives_considered"), list)
    assert isinstance(outputs.get("uncertainties"), list)
    assert isinstance(outputs.get("failure_modes"), list)
    assert outputs.get("confidence_level") in {"low", "medium", "high"}

    # Hardened audit envelope contract
    assert meta.get("skill_id") == "decision.make"
    assert isinstance(meta.get("trace_id"), str) and meta.get("trace_id")
    assert meta.get("status") == "completed"
    assert isinstance(meta.get("steps_count"), int) and meta["steps_count"] >= 1
    assert isinstance(meta.get("completed_steps_count"), int)
    assert isinstance(meta.get("failed_steps_count"), int)
    assert (
        meta["completed_steps_count"] + meta["failed_steps_count"]
        == meta["steps_count"]
    )

    # Fallback and step diagnostics contract
    assert isinstance(meta.get("fallback_used"), bool)
    assert isinstance(meta.get("fallback_steps_count"), int)
    assert isinstance(meta.get("fallback_steps"), list)
    assert isinstance(meta.get("step_diagnostics"), list)
    assert len(meta["step_diagnostics"]) == meta["steps_count"]

    for step in meta["step_diagnostics"]:
        assert isinstance(step.get("step_id"), str) and step["step_id"]
        assert isinstance(step.get("uses"), str) and step["uses"]
        assert isinstance(step.get("status"), str) and step["status"]
        assert (
            isinstance(step.get("duration_ms"), (int, float))
            and step["duration_ms"] >= 0
        )
        assert isinstance(step.get("fallback_used"), bool)
        assert (
            isinstance(step.get("attempts_count"), int) and step["attempts_count"] >= 1
        )


def test_decision_make_step_diagnostics_are_auditable():
    result = execute_with_meta(
        "decision.make",
        {
            "goal": "Decide whether to build full product or MVP for a new vertical.",
            "risk_tolerance": "medium",
        },
    )

    meta = result["meta"]
    step_ids = {step["step_id"] for step in meta["step_diagnostics"]}

    # Expected decision.make pipeline traceability
    expected_steps = {
        "merge_context",
        "generate_options",
        "analyze_options",
        "evaluate_options",
        "justify_decision",
        "assess_quality",
    }
    assert expected_steps.issubset(step_ids)

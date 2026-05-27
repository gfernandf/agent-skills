from __future__ import annotations

import os
from typing import Any

import pytest

from sdk.embedded import execute_capability, reset
from test_cognitive_capabilities_e2e import (
    _build_inputs,
    _load_active_cognitive_capabilities,
)


def _capability_index() -> dict[str, dict[str, Any]]:
    return {c["id"]: c for c in _load_active_cognitive_capabilities()}


def _payload(cap_id: str, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    cap = _capability_index()[cap_id]
    base = _build_inputs(cap)
    if overrides:
        base.update(overrides)
    return base


@pytest.fixture(autouse=True)
def _force_local_python_fallback() -> None:
    prev = os.environ.pop("OPENAI_API_KEY", None)
    reset()
    yield
    if prev is not None:
        os.environ["OPENAI_API_KEY"] = prev
    reset()


def test_semantic_pipeline_decision_reasoning_perception() -> None:
    structured = execute_capability(
        "perception.input.structure",
        _payload(
            "perception.input.structure",
            {
                "fields": [
                    {
                        "name": "goal",
                        "type": "string",
                        "required": True,
                        "description": "Decision objective",
                    },
                    {
                        "name": "context",
                        "type": "string",
                        "required": True,
                        "description": "Execution context",
                    },
                ],
                "raw_input": {
                    "goal": "Seleccionar estrategia de lanzamiento para nuevo SaaS B2B",
                    "context": "Equipo pequeño, horizonte 12 meses, competencia establecida",
                },
            },
        ),
    )
    assert structured["complete"] is True
    assert isinstance(structured["structured_input"], dict)
    assert "goal" in structured["structured_input"]

    interpreted = execute_capability(
        "reasoning.goal.interpret",
        _payload(
            "reasoning.goal.interpret",
            {
                "normalized_request": {
                    "raw_request": structured["structured_input"]["goal"],
                    "detected_intent": "decision_support",
                }
            },
        ),
    )
    interpreted_goal = interpreted["interpreted_goal"]
    assert isinstance(interpreted_goal, dict)
    assert isinstance(interpreted_goal.get("objective"), str)
    assert interpreted_goal.get("objective", "").strip() != ""

    generated = execute_capability(
        "reasoning.option.generate",
        _payload("reasoning.option.generate", {"goal": interpreted_goal["objective"]}),
    )
    options = generated["options"]
    option_ids = [o.get("id") for o in options if isinstance(o, dict)]
    assert len(options) >= 2
    assert len(set(option_ids)) == len(option_ids)

    analyzed = execute_capability(
        "reasoning.option.analyze",
        _payload(
            "reasoning.option.analyze",
            {
                "options": options,
                "goal": interpreted_goal["objective"],
            },
        ),
    )
    analyzed_options = analyzed["analyzed_options"]
    analyzed_ids = {
        a.get("option_id")
        for a in analyzed_options
        if isinstance(a, dict) and isinstance(a.get("option_id"), str)
    }
    assert analyzed_ids.issubset(set(option_ids))
    assert analyzed_ids

    scored = execute_capability(
        "evaluation.option.score",
        _payload(
            "evaluation.option.score",
            {
                "options": options,
                "goal": interpreted_goal["objective"],
            },
        ),
    )
    scored_options = scored["scored_options"]
    scored_ids = {
        s.get("option_id")
        for s in scored_options
        if isinstance(s, dict) and isinstance(s.get("option_id"), str)
    }
    assert scored_ids.issubset(set(option_ids))
    assert scored_ids

    selected = execute_capability(
        "decision.option.select",
        _payload(
            "decision.option.select",
            {
                "options": options,
                "option_scores": scored_options,
                "option_analysis": analyzed_options,
            },
        ),
    )
    selected_option = selected["selected_option"]
    selected_id = (
        selected_option.get("id") if isinstance(selected_option, dict) else None
    )
    assert isinstance(selected_id, str)
    assert selected_id in option_ids

    rejected = selected.get("rejected_options", [])
    rejected_ids = {
        r.get("option")
        for r in rejected
        if isinstance(r, dict) and isinstance(r.get("option"), str)
    }
    assert selected_id not in rejected_ids


def test_semantic_pipeline_evidence_uncertainty_hypotheses() -> None:
    hypotheses_out = execute_capability(
        "reasoning.hypothesis.generate",
        _payload(
            "reasoning.hypothesis.generate",
            {
                "goal": "Explicar caida de conversion del onboarding",
                "context": "Dropoff concentrado en paso de verificacion",
            },
        ),
    )
    hypotheses = hypotheses_out["hypotheses"]
    hypothesis_ids = {
        h.get("id")
        for h in hypotheses
        if isinstance(h, dict) and isinstance(h.get("id"), str)
    }
    assert hypothesis_ids

    evaluated_out = execute_capability(
        "evaluation.hypothesis.evaluate",
        _payload(
            "evaluation.hypothesis.evaluate",
            {
                "hypotheses": hypotheses,
                "evidence": [
                    {"id": "e-1", "text": "Dropoff subio de 18% a 41% en el paso 2"},
                    {
                        "id": "e-2",
                        "text": "No hubo cambios en pricing durante el periodo",
                    },
                ],
            },
        ),
    )
    evaluated = evaluated_out["evaluated_hypotheses"]
    evaluated_ids = {
        h.get("hypothesis_id")
        for h in evaluated
        if isinstance(h, dict) and isinstance(h.get("hypothesis_id"), str)
    }
    assert evaluated_ids.issubset(hypothesis_ids)
    assert evaluated_ids

    compared_out = execute_capability(
        "evaluation.hypothesis.compare",
        _payload(
            "evaluation.hypothesis.compare",
            {
                "evaluated_hypotheses": evaluated,
                "comparison_axes": ["plausibility", "actionability"],
            },
        ),
    )
    ranked = compared_out["ranked_hypotheses"]
    ranked_ids = [
        r.get("hypothesis_id")
        for r in ranked
        if isinstance(r, dict) and isinstance(r.get("hypothesis_id"), str)
    ]
    assert ranked_ids
    recommendation = compared_out["recommendation"]
    lead = (
        recommendation.get("lead_hypothesis")
        if isinstance(recommendation, dict)
        else None
    )
    assert lead in ranked_ids

    uncertainties_out = execute_capability(
        "reasoning.uncertainty.extract",
        _payload(
            "reasoning.uncertainty.extract",
            {
                "target": {
                    "id": "plan-1",
                    "text": "Plan de lanzamiento con dependencias externas y timing rigido",
                }
            },
        ),
    )
    uncertainties = uncertainties_out["uncertainties"]
    uncertainty_ids = {
        u.get("id")
        for u in uncertainties
        if isinstance(u, dict) and isinstance(u.get("id"), str)
    }
    assert uncertainty_ids

    scored_uncertainties_out = execute_capability(
        "evaluation.uncertainty.score",
        _payload(
            "evaluation.uncertainty.score",
            {"uncertainties": uncertainties},
        ),
    )
    scored_uncertainties = scored_uncertainties_out["scored_uncertainties"]
    scored_ids = {
        u.get("uncertainty_id")
        for u in scored_uncertainties
        if isinstance(u, dict) and isinstance(u.get("uncertainty_id"), str)
    }
    assert scored_ids.issubset(uncertainty_ids)
    assert scored_ids

    prioritized_out = execute_capability(
        "decision.uncertainty.prioritize",
        _payload(
            "decision.uncertainty.prioritize",
            {
                "scored_uncertainties": scored_uncertainties,
                "capacity_limit": 1,
            },
        ),
    )
    prioritized = prioritized_out["prioritized_uncertainties"]
    assert 1 <= len(prioritized) <= 1
    top_uid = (
        prioritized[0].get("uncertainty_id")
        if isinstance(prioritized[0], dict)
        else None
    )
    assert top_uid in scored_ids

    source_assessment_out = execute_capability(
        "evidence.source.assess",
        _payload(
            "evidence.source.assess",
            {
                "sources": [
                    {"id": "s1", "title": "Informe de mercado"},
                    {"id": "s2", "title": "Reporte financiero"},
                ]
            },
        ),
    )
    source_scores = source_assessment_out["source_scores"]
    assert source_scores
    for source in source_scores:
        assert 0.0 <= float(source["overall"]) <= 1.0


def test_semantic_pipeline_output_packaging_and_memory() -> None:
    interpreted_out = execute_capability(
        "reasoning.goal.interpret",
        _payload(
            "reasoning.goal.interpret",
            {
                "normalized_request": {
                    "raw_request": "Entregar recomendacion de lanzamiento con plan accionable",
                    "detected_intent": "decision_support",
                }
            },
        ),
    )
    interpreted_goal = interpreted_out["interpreted_goal"]

    response_out = execute_capability(
        "reasoning.response.generate",
        _payload(
            "reasoning.response.generate",
            {
                "interpreted_goal": interpreted_goal,
                "selected_option": {"id": "opt-1", "label": "Lanzar MVP"},
                "execution_result": {
                    "recommendation": "Lanzar MVP",
                    "confidence_score": 0.64,
                    "next_steps": ["validar supuestos", "ejecutar piloto"],
                },
            },
        ),
    )
    report = response_out["report"]
    assert isinstance(report, dict)
    assert isinstance(report.get("user_response"), str)
    assert report.get("user_response", "").strip() != ""
    assert isinstance(report.get("artifacts"), list)
    assert report["artifacts"]
    assert response_out["report_status"] in {
        "success",
        "partial",
        "failed",
        "requires_followup",
    }

    store_out = execute_capability(
        "memory.context.store",
        _payload(
            "memory.context.store",
            {
                "context_id": "ctx-golden-1",
                "context": {
                    "goal": interpreted_goal.get("objective"),
                    "recommendation": "Lanzar MVP",
                },
            },
        ),
    )
    assert store_out["stored"] is True
    assert isinstance(store_out["context_id"], str)
    assert store_out["context_id"].strip() != ""

    retrieve_out = execute_capability(
        "memory.context.retrieve",
        _payload(
            "memory.context.retrieve",
            {"context_id": store_out["context_id"]},
        ),
    )
    assert isinstance(retrieve_out["context"], dict)
    assert isinstance(retrieve_out["found"], bool)

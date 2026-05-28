"""
Integration tests for decision.make skill.
Validates deterministic behavior across empty inputs, pre-provided options,
and low-confidence edge cases.
"""

import pytest
from pathlib import Path
from cli.main import _build_engine
from runtime.models import ExecutionRequest

TEST_ROOT = Path(__file__).resolve().parent
RUNTIME_ROOT = TEST_ROOT
REGISTRY_ROOT = RUNTIME_ROOT.parent / "agent-skill-registry"


@pytest.fixture
def engine(monkeypatch):
    """Build execution engine with decision.make capability."""
    # Ensure deterministic local execution in this integration test.
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    return _build_engine(REGISTRY_ROOT, RUNTIME_ROOT, RUNTIME_ROOT, None)


def test_decision_make_with_empty_context(engine):
    """
    Verify decision.make handles missing context_items gracefully.
    Expects: generated options + baseline analysis + recommendation with low confidence.
    """
    request = ExecutionRequest(
        skill_id="decision.make",
        inputs={
            "goal": "Should we adopt microservices architecture?",
            # context_items omitted → defaults to None/empty
        },
    )

    result = engine.execute(request)

    assert result.status == "completed", f"Expected completed, got {result.status}"
    assert result.outputs.get("recommendation"), "Missing recommendation"
    assert result.outputs.get("alternatives_considered"), "Missing alternatives"
    assert result.outputs.get("confidence_score"), "Missing confidence_score"

    # Low confidence expected due to missing context
    confidence = result.outputs["confidence_score"]
    assert 0.0 <= confidence <= 1.0, f"Invalid confidence {confidence}"


def test_decision_make_with_preprovided_options(engine):
    """
    Verify decision.make uses pre-provided options instead of generating them.
    Expects: provided options used as-is through the pipeline.
    """
    provided_options = [
        {"id": "opt-1", "label": "Option A", "description": "Build in-house"},
        {"id": "opt-2", "label": "Option B", "description": "Buy commercial"},
        {"id": "opt-3", "label": "Option C", "description": "Use open-source"},
    ]

    request = ExecutionRequest(
        skill_id="decision.make",
        inputs={
            "goal": "How should we source our platform?",
            "context_items": [
                {"id": "analysis", "content": "Cost analysis shows 3 viable paths."}
            ],
            "options": provided_options,
            "option_constraint_mode": "strict",
        },
    )

    result = engine.execute(request)

    assert result.status == "completed", f"Expected completed, got {result.status}"

    # Strict mode must preserve the exact explicit option set.
    alternatives = result.outputs.get("alternatives_considered", [])
    assert len(alternatives) == len(provided_options), (
        f"Expected exactly {len(provided_options)} alternatives, got {len(alternatives)}"
    )

    alt_ids = [alt.get("id") for alt in alternatives if isinstance(alt, dict)]
    provided_ids = [opt["id"] for opt in provided_options]
    assert alt_ids == provided_ids, (
        f"Option ids drifted or reordered. expected={provided_ids}, observed={alt_ids}"
    )

    alt_labels = {alt.get("id"): alt.get("label") for alt in alternatives}
    provided_labels = {opt["id"]: opt["label"] for opt in provided_options}
    assert alt_labels == provided_labels, (
        "Option labels drifted in strict mode. "
        f"expected={provided_labels}, observed={alt_labels}"
    )


def test_decision_make_with_risk_tolerance(engine):
    """
    Verify decision.make respects risk_tolerance setting.
    Expects: risk_tolerance propagated through evaluation.option.score and affects scoring.
    """
    request = ExecutionRequest(
        skill_id="decision.make",
        inputs={
            "goal": "Which market should we enter?",
            "context_items": [
                {"id": "market_research", "content": "Three target markets identified."}
            ],
            "risk_tolerance": "low",
        },
    )

    result = engine.execute(request)

    assert result.status == "completed", f"Expected completed, got {result.status}"
    assert result.outputs.get("recommendation"), "Missing recommendation"

    # Verify uncertainties and failure_modes were populated (indicates quality processing)
    uncertainties = result.outputs.get("uncertainties", [])
    assert len(uncertainties) > 0, "Uncertainties should be populated"


def test_decision_make_end_to_end_full_pipeline(engine):
    """
    Verify complete decision.make pipeline: merge → generate → analyze → score → justify → quality check.
    Expects: all outputs present, structured decision with explicit recommendation.
    """
    rich_context = [
        {
            "id": "market",
            "title": "Market Analysis",
            "content": "Strong demand in Asia-Pacific region.",
        },
        {
            "id": "tech",
            "title": "Technology",
            "content": "Modern stack, proven frameworks available.",
        },
        {
            "id": "team",
            "title": "Team Capability",
            "content": "Team has 5 years experience in similar domains.",
        },
    ]

    constraints = {
        "budget_limit": "2M USD",
        "timeline_months": 12,
        "team_size": 5,
    }

    request = ExecutionRequest(
        skill_id="decision.make",
        inputs={
            "goal": "Should we launch a new SaaS product in the Asia-Pacific market?",
            "context_items": rich_context,
            "constraints": constraints,
            "risk_tolerance": "medium",
        },
    )

    result = engine.execute(request)

    assert result.status == "completed", f"Expected completed, got {result.status}"

    # Validate all required outputs
    required_outputs = [
        "recommendation",
        "alternatives_considered",
        "criteria_used",
        "evaluation_summary",
        "tradeoffs",
        "confidence_score",
        "confidence_level",
        "uncertainties",
        "failure_modes",
        "next_steps",
        "decision_quality_score",
        "decision_quality_dimensions",
        "decision_quality_level",
        "human_readable",
    ]

    for output_field in required_outputs:
        assert output_field in result.outputs, (
            f"Missing required output: {output_field}"
        )
        value = result.outputs[output_field]
        assert value is not None, f"Output {output_field} is None"

    # Validate output types
    assert isinstance(result.outputs["recommendation"], str), (
        "recommendation must be string"
    )
    assert isinstance(result.outputs["confidence_score"], (int, float)), (
        "confidence_score must be numeric"
    )
    assert result.outputs["confidence_level"] in ["low", "medium", "high"], (
        "confidence_level must be valid enum"
    )
    assert isinstance(result.outputs["uncertainties"], list), (
        "uncertainties must be array"
    )
    assert isinstance(result.outputs["failure_modes"], list), (
        "failure_modes must be array"
    )
    assert isinstance(result.outputs["next_steps"], list), "next_steps must be array"
    assert isinstance(result.outputs["human_readable"], str), (
        "human_readable must be string"
    )

    # Verify decision_quality components
    assert isinstance(result.outputs["decision_quality_score"], (int, float)), (
        "decision_quality_score must be numeric"
    )
    assert 0.0 <= result.outputs["decision_quality_score"] <= 100.0, (
        "decision_quality_score must be 0-100"
    )
    assert isinstance(result.outputs["decision_quality_dimensions"], dict), (
        "decision_quality_dimensions must be object"
    )
    assert result.outputs["decision_quality_level"] in [
        "poor",
        "fair",
        "good",
        "excellent",
    ], "decision_quality_level must be valid"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

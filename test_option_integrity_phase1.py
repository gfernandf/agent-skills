"""Unit tests for phase-1 option integrity helpers and decision fallback behavior."""

from runtime.entity_integrity import detect_option_drift
from official_services.decision_baseline import justify_option


def test_detect_option_drift_finds_missing_new_and_renamed() -> None:
    expected = [
        {"id": "opt-1", "label": "Option A"},
        {"id": "opt-2", "label": "Option B"},
    ]
    observed = [
        {"id": "opt-1", "label": "Option A Renamed"},
        {"id": "opt-3", "label": "Option C"},
    ]

    drift = detect_option_drift(expected, observed)

    assert drift["has_drift"] is True
    assert drift["missing_ids"] == ["opt-2"]
    assert drift["new_ids"] == ["opt-3"]
    assert drift["renamed"][0]["id"] == "opt-1"


def test_justify_option_downgrades_confidence_on_strict_drift() -> None:
    explicit_options = [
        {"id": "opt-1", "label": "Option A"},
        {"id": "opt-2", "label": "Option B"},
    ]
    # Drifted scored options: opt-2 missing, opt-3 added, opt-1 renamed.
    scored_options = [
        {"option_id": "opt-1", "label": "Option A Renamed", "overall_score": 90.0},
        {"option_id": "opt-3", "label": "Option C", "overall_score": 89.0},
    ]

    result = justify_option(
        scored_options=scored_options,
        analyzed_options=[],
        goal="Choose platform",
        explicit_options=explicit_options,
        option_constraint_mode="strict",
    )

    alt_ids = [item["id"] for item in result["alternatives_considered"]]
    assert alt_ids == ["opt-1", "opt-2"]
    assert result["confidence_level"] == "low"
    assert result["confidence_score"] <= 0.3
    assert any("Strict option integrity mode" in text for text in result["uncertainties"])


def test_justify_option_uses_conservative_tie_break_for_equal_scores() -> None:
    scored_options = [
        {"option_id": "opt-1", "label": "construir producto completo", "overall_score": 90.0},
        {"option_id": "opt-2", "label": "lanzar piloto/MVP", "overall_score": 90.0},
        {"option_id": "opt-3", "label": "posponer", "overall_score": 90.0},
    ]

    result = justify_option(
        scored_options=scored_options,
        analyzed_options=[],
        goal="Decidir estrategia de lanzamiento",
    )

    assert "lanzar piloto/MVP" in result["recommendation"]
    assert result["confidence_score"] <= 0.55
    assert any(
        "heuristic baseline scoring scale" in text for text in result["uncertainties"]
    )

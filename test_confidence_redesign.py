"""
Test suite for redesigned multicomponent confidence scoring.

Validates that confidence_score is consistent with decision quality,
option separation, and other factors — not overly pessimistic.
"""

import pytest
from official_services.decision_baseline import (
    _confidence_level_from_score,
    _compute_execution_reliability,
    _compute_information_completeness,
    _compute_option_separation_strength,
    _compute_uncertainty_level,
    _compute_fallback_severity,
    _compute_multicomponent_confidence,
    justify_option,
)


class TestConfidenceComponentScoring:
    """Test individual confidence components."""

    def test_confidence_level_boundary_at_point_seven(self):
        """0.70 is classified as medium to avoid overlap with high."""
        assert _confidence_level_from_score(0.70) == "medium"
        assert _confidence_level_from_score(0.7001) == "high"

    def test_execution_reliability_clean(self):
        """Clean execution (no fallback, no drift) should have high reliability."""
        score = _compute_execution_reliability(
            best_score=0.8, high_scale_scores=False, drift_detected=False
        )
        assert score == 1.0, "Clean execution should have 1.0 reliability"

    def test_execution_reliability_heuristic_fallback(self):
        """Heuristic fallback (0-100 scale) should lower reliability but not collapse."""
        score = _compute_execution_reliability(
            best_score=0.8, high_scale_scores=True, drift_detected=False
        )
        assert 0.80 <= score <= 0.90, f"Heuristic fallback should be ~0.85, got {score}"

    def test_execution_reliability_drift(self):
        """Entity drift is more serious but still not zero."""
        score = _compute_execution_reliability(
            best_score=0.8, high_scale_scores=False, drift_detected=True
        )
        assert 0.50 <= score <= 0.70, f"Drift should degrade to ~0.6, got {score}"

    def test_information_completeness_rich(self):
        """Rich inputs should score high."""
        scored_opts = [
            {"option_id": "opt1", "label": "Option 1", "overall_score": 0.8},
            {"option_id": "opt2", "label": "Option 2", "overall_score": 0.5},
            {"option_id": "opt3", "label": "Option 3", "overall_score": 0.4},
            {"option_id": "opt4", "label": "Option 4", "overall_score": 0.3},
        ]
        analyzed_opts = [
            {"option_id": "opt1", "pros": ["A", "B"], "cons": ["C"]},
            {"option_id": "opt2", "pros": ["D"], "cons": ["E", "F"]},
        ]
        score = _compute_information_completeness(
            scored_options=scored_opts,
            analyzed_options=analyzed_opts,
            context_provided=True,
        )
        assert score >= 0.65, f"Rich inputs should score >=0.65, got {score}"

    def test_option_separation_clear_winner(self):
        """Clear margin between options (0.8 vs 0.5 vs 0.4) should score high."""
        scored_opts = [
            {"option_id": "opt1", "label": "MVP", "overall_score": 80.0},
            {"option_id": "opt2", "label": "Full", "overall_score": 50.0},
            {"option_id": "opt3", "label": "Defer", "overall_score": 40.0},
        ]
        score = _compute_option_separation_strength(scored_opts)
        # Margin = (80-50)/80 = 0.375, which is > 0.3 → should be 0.95
        assert score >= 0.90, f"Clear winner should score >=0.9, got {score}"

    def test_option_separation_close_race(self):
        """Close margin (0.65 vs 0.63) should score lower."""
        scored_opts = [
            {"option_id": "opt1", "label": "Option A", "overall_score": 0.65},
            {"option_id": "opt2", "label": "Option B", "overall_score": 0.63},
            {"option_id": "opt3", "label": "Option C", "overall_score": 0.60},
        ]
        score = _compute_option_separation_strength(scored_opts)
        # Margin = (0.65-0.63)/0.65 = 0.03, which is < 0.15 → should be 0.4
        assert score <= 0.50, f"Close race should score <=0.5, got {score}"

    def test_uncertainty_mature_domain(self):
        """Mature domain (no novelty) should have high uncertainty score."""
        score = _compute_uncertainty_level(
            goal="Should we upgrade our existing SaaS?", has_domain_uncertainty=False
        )
        assert score == 1.0, "Mature domain should have 1.0 uncertainty score"

    def test_uncertainty_new_domain(self):
        """New domain should lower uncertainty score but not collapse."""
        score = _compute_uncertainty_level(
            goal="We have no experience in legaltech", has_domain_uncertainty=True
        )
        assert score == 0.70, "New domain should have 0.70 uncertainty score"

    def test_fallback_severity_no_fallback(self):
        """No fallback should have high severity score."""
        score = _compute_fallback_severity(high_scale_scores=False)
        assert score == 1.0, "No fallback should have 1.0 severity score"

    def test_fallback_severity_heuristic(self):
        """Heuristic fallback should lower but not collapse."""
        score = _compute_fallback_severity(high_scale_scores=True)
        assert 0.80 <= score <= 0.90, f"Heuristic fallback should be ~0.85, got {score}"


class TestMulticomponentConfidence:
    """Test multicomponent confidence scoring."""

    def test_saas_legaltech_scenario(self):
        """
        Test the problematic scenario from the user:
        - decision_quality_score = 85 (good)
        - selected option = 0.8 (clear winner vs 0.5, 0.4)
        - 1 fallback of 6 steps (minor)
        - domain_uncertainty = True (legaltech is new)

        Expected: confidence ≈ 0.55-0.70 (medium level)
        Previous: 0.01 (WRONG)
        """
        scored_opts = [
            {"option_id": "opt1", "label": "Build full product", "overall_score": 50.0},
            {"option_id": "opt2", "label": "MVP", "overall_score": 80.0},
            {"option_id": "opt3", "label": "Defer", "overall_score": 40.0},
        ]
        analyzed_opts = [
            {"option_id": "opt1", "pros": ["Complete"], "cons": ["Expensive", "Risky"]},
            {"option_id": "opt2", "pros": ["Fast", "Validated"], "cons": ["Limited"]},
            {"option_id": "opt3", "pros": ["Safe"], "cons": ["Lose market"]},
        ]

        confidence = _compute_multicomponent_confidence(
            scored_options=scored_opts,
            analyzed_options=analyzed_opts,
            context_provided=True,
            best_score=80.0,
            high_scale_scores=True,  # Heuristic fallback (0-100 scale)
            drift_detected=False,
            has_domain_uncertainty=True,  # legaltech = new domain
            goal="We have no experience in legaltech but want to launch SaaS",
        )

        print(f"\nSaaS legaltech confidence: {confidence}")
        assert 0.50 <= confidence <= 0.75, (
            f"SaaS legaltech case should be 0.50-0.75 (medium), got {confidence}"
        )

    def test_mature_domain_high_confidence(self):
        """
        Mature domain with good execution should have higher confidence.
        """
        scored_opts = [
            {"option_id": "opt1", "label": "Option A", "overall_score": 0.75},
            {"option_id": "opt2", "label": "Option B", "overall_score": 0.50},
            {"option_id": "opt3", "label": "Option C", "overall_score": 0.40},
        ]
        analyzed_opts = [
            {"option_id": "opt1", "pros": ["Good"], "cons": ["Minor issue"]},
            {"option_id": "opt2", "pros": ["OK"], "cons": ["Not ideal"]},
        ]

        confidence = _compute_multicomponent_confidence(
            scored_options=scored_opts,
            analyzed_options=analyzed_opts,
            context_provided=True,
            best_score=0.75,
            high_scale_scores=False,  # Clean LLM scoring
            drift_detected=False,
            has_domain_uncertainty=False,  # Mature domain
            goal="Should we upgrade our infrastructure?",
        )

        print(f"\nMature domain confidence: {confidence}")
        assert confidence >= 0.70, (
            f"Mature domain with good execution should be >=0.70, got {confidence}"
        )

    def test_sparse_inputs_lower_confidence(self):
        """
        Sparse inputs should lower confidence moderately.
        """
        scored_opts = [
            {"option_id": "opt1", "label": "Option A", "overall_score": 0.8},
        ]
        analyzed_opts = []  # No analysis

        confidence = _compute_multicomponent_confidence(
            scored_options=scored_opts,
            analyzed_options=analyzed_opts,
            context_provided=False,  # No context
            best_score=0.8,
            high_scale_scores=False,
            drift_detected=False,
            has_domain_uncertainty=False,
            goal="Simple decision",
        )

        print(f"\nSparse inputs confidence: {confidence}")
        assert 0.40 <= confidence <= 0.70, (
            f"Sparse inputs should lower but not collapse (0.40-0.70), got {confidence}"
        )

    def test_close_race_lower_confidence(self):
        """
        Close margin between options should lower confidence.
        """
        scored_opts = [
            {"option_id": "opt1", "label": "Option A", "overall_score": 0.62},
            {"option_id": "opt2", "label": "Option B", "overall_score": 0.60},
        ]
        analyzed_opts = [
            {"option_id": "opt1", "pros": ["A"], "cons": ["X"]},
            {"option_id": "opt2", "pros": ["B"], "cons": ["Y"]},
        ]

        confidence = _compute_multicomponent_confidence(
            scored_options=scored_opts,
            analyzed_options=analyzed_opts,
            context_provided=True,
            best_score=0.62,
            high_scale_scores=False,
            drift_detected=False,
            has_domain_uncertainty=False,
            goal="Choose between two similar options",
        )

        print(f"\nClose race confidence: {confidence}")
        assert confidence <= 0.60, (
            f"Close race should have lower confidence (<=0.60), got {confidence}"
        )


class TestJustifyOptionWithNewConfidence:
    """Test justify_option() function with new confidence logic."""

    def test_saas_case_full_flow(self):
        """
        Full flow test: justify_option with SaaS legaltech scenario.
        """
        scored_opts = [
            {"option_id": "opt1", "label": "Build full product", "overall_score": 50.0},
            {"option_id": "opt2", "label": "MVP", "overall_score": 80.0},
            {"option_id": "opt3", "label": "Defer", "overall_score": 40.0},
        ]
        analyzed_opts = [
            {"option_id": "opt1", "pros": ["Complete"], "cons": ["Expensive", "Risk"]},
            {"option_id": "opt2", "pros": ["Fast", "Learn"], "cons": ["Limited"]},
            {"option_id": "opt3", "pros": ["Safe"], "cons": ["Late"]},
        ]

        result = justify_option(
            scored_options=scored_opts,
            analyzed_options=analyzed_opts,
            goal="We have no experience in legaltech. Launch SaaS?",
            tradeoffs=["Completeness vs Speed"],
            risk_tolerance="medium",
        )

        print("\nFull flow result:")
        print(f"  Recommendation: {result['recommendation']}")
        print(f"  Confidence score: {result['confidence_score']}")
        print(f"  Confidence level: {result['confidence_level']}")
        print(f"  Quality score: {result.get('decision_quality_score', 'N/A')}")

        # Check that confidence is reasonable, not collapsed to 0.01
        assert result["confidence_score"] >= 0.50, (
            f"Confidence should be >=0.50 for clear winner, got {result['confidence_score']}"
        )

        # Check that level is consistent with score
        if result["confidence_score"] < 0.30:
            assert result["confidence_level"] == "low"
        elif result["confidence_score"] <= 0.70:
            assert result["confidence_level"] == "medium"
        else:
            assert result["confidence_level"] == "high"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

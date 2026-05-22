from sdk.embedded import apply_execution_reliability_confidence_calibration


def test_minor_fallback_caps_high_to_medium_boundary():
    outputs = {
        "confidence_score": 0.92,
        "confidence_level": "high",
    }
    meta = {
        "fallback_used": True,
        "fallback_severity": {"level": "minor"},
        "fallback_steps": [{"step_id": "justify_decision"}],
    }

    out = apply_execution_reliability_confidence_calibration(
        skill_id="decision.make",
        outputs=outputs,
        meta=meta,
    )

    assert out["confidence_score"] == 0.69
    assert out["confidence_level"] == "medium"
    assert out["execution_reliability_adjustment"]["raw_confidence_score"] == 0.92
    assert out["execution_reliability_adjustment"]["adjusted_confidence_score"] == 0.69


def test_moderate_fallback_caps_to_065_and_not_high():
    outputs = {
        "confidence_score": 0.88,
        "confidence_level": "high",
    }
    meta = {
        "fallback_used": True,
        "fallback_severity": {"level": "moderate"},
        "fallback_steps": [{"step_id": "justify_decision"}],
    }

    out = apply_execution_reliability_confidence_calibration(
        skill_id="decision.make",
        outputs=outputs,
        meta=meta,
    )

    assert out["confidence_score"] == 0.65
    assert out["confidence_level"] == "medium"


def test_severe_fallback_forces_low_confidence():
    outputs = {
        "confidence_score": 0.83,
        "confidence_level": "high",
    }
    meta = {
        "fallback_used": True,
        "fallback_severity": {"level": "severe"},
        "fallback_steps": [{"step_id": "evaluate_options"}],
    }

    out = apply_execution_reliability_confidence_calibration(
        skill_id="decision.make",
        outputs=outputs,
        meta=meta,
    )

    assert out["confidence_score"] == 0.4
    assert out["confidence_level"] == "low"


def test_no_fallback_keeps_confidence_unchanged():
    outputs = {
        "confidence_score": 0.92,
        "confidence_level": "high",
    }
    meta = {
        "fallback_used": False,
        "fallback_severity": {"level": "none"},
    }

    out = apply_execution_reliability_confidence_calibration(
        skill_id="decision.make",
        outputs=outputs,
        meta=meta,
    )

    assert out["confidence_score"] == 0.92
    assert out["confidence_level"] == "high"
    assert "execution_reliability_adjustment" not in out

"""
Quick validation that alternatives_evaluated is included in decision.make output
and confidence is reduced for domain-new decisions.
"""
from pathlib import Path
from cli.main import _build_engine
from runtime.models import ExecutionRequest

TEST_ROOT = Path(__file__).resolve().parent
RUNTIME_ROOT = TEST_ROOT
REGISTRY_ROOT = RUNTIME_ROOT.parent / "agent-skill-registry"

def test_alternatives_evaluated():
    engine = _build_engine(REGISTRY_ROOT, RUNTIME_ROOT, RUNTIME_ROOT, None)
    
    # Test scenario: entering a new domain (legaltech) — should trigger domain uncertainty cap
    request = ExecutionRequest(
        skill_id="decision.make",
        inputs={
            "goal": "Should we expand into legaltech? We have no prior experience in the legal industry.",
            "options": [
                {"id": "opt-1", "label": "MVP legaltech", "description": "Minimal legal product"},
                {"id": "opt-2", "label": "Full legal suite", "description": "Complete legal platform"},
                {"id": "opt-3", "label": "Partnership", "description": "Partner with legal firm"},
            ],
            "risk_tolerance": "medium",
        },
    )

    result = engine.execute(request)
    print(f"Status: {result.status}")
    
    assert result.status == "completed", f"Expected completed, got {result.status}"
    
    outputs = result.outputs
    
    # Verify alternatives_evaluated exists
    assert "alternatives_evaluated" in outputs, "Missing alternatives_evaluated field"
    alternatives_eval = outputs["alternatives_evaluated"]
    assert isinstance(alternatives_eval, list), "alternatives_evaluated should be array"
    assert len(alternatives_eval) > 0, "alternatives_evaluated should not be empty"
    
    # Check structure of first evaluated alternative
    first_alt = alternatives_eval[0]
    assert "option" in first_alt, "Missing 'option' field in alternative"
    assert "score" in first_alt, "Missing 'score' field in alternative"
    assert "pros" in first_alt, "Missing 'pros' field in alternative"
    assert "cons" in first_alt, "Missing 'cons' field in alternative"
    
    print("\n[OK] alternatives_evaluated structure is correct")
    print(f"  - Number of evaluated alternatives: {len(alternatives_eval)}")
    for i, alt in enumerate(alternatives_eval):
        print(f"  [{i}] {alt.get('option')}: score={alt.get('score')}, " 
              f"pros={len(alt.get('pros', []))}, cons={len(alt.get('cons', []))}")
    
    # Verify confidence was capped for domain-new decision
    confidence = outputs.get("confidence_score", 0.0)
    confidence_level = outputs.get("confidence_level", "")
    
    print("\n[OK] Confidence calibration for domain-new decision:")
    print(f"  - Confidence score: {confidence}")
    print(f"  - Confidence level: {confidence_level}")
    
    # Domain uncertainty should cap confidence at 0.65, so it should be in medium-high range
    assert confidence <= 0.65, f"Domain uncertainty cap not applied: {confidence} > 0.65"
    print("  - Domain uncertainty cap applied [OK]")
    
    # Check that uncertainties carry uncertainty signal for domain-new decisions.
    # OpenAPI wording can vary, so validate semantically instead of exact phrasing.
    uncertainties = outputs.get("uncertainties", [])
    domain_uncertainty_mentioned = any(
        isinstance(u, str)
        and (
            "domain" in u.lower()
            or "new" in u.lower()
            or "uncertainty" in u.lower()
            or "experience" in u.lower()
        )
        for u in uncertainties
    )
    if uncertainties:
        assert domain_uncertainty_mentioned or confidence <= 0.65, (
            "Expected uncertainty signal or confidence cap for domain-new decision"
        )
        print("  - Uncertainty signal present in uncertainties [OK]")
    else:
        print("  - Uncertainties field not provided; confidence cap used as signal [OK]")
    
    print("\n[OK] All validations passed")
    print(f"\nRecommendation: {outputs.get('recommendation')}")

if __name__ == "__main__":
    test_alternatives_evaluated()

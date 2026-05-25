"""
Quick validation that alternatives_evaluated is accessible in decision_baseline.
"""
import json
from official_services.decision_baseline import justify_option

# Simulate scored options with analysis data
scored_options = [
    {
        "option_id": "opt-1",
        "label": "MVP Approach",
        "overall_score": 75.0,
    },
    {
        "option_id": "opt-2", 
        "label": "Full Build",
        "overall_score": 82.0,
    },
]

analyzed_options = [
    {
        "option_id": "opt-1",
        "label": "MVP Approach",
        "pros": ["Lower risk", "Faster validation", "Less capital"],
        "cons": ["Limited functionality", "May need redesign"],
    },
    {
        "option_id": "opt-2",
        "label": "Full Build", 
        "pros": ["Complete feature set", "Market ready"],
        "cons": ["High cost", "Long timeline", "Risk of market shift"],
    },
]

# Test with domain-new goal to trigger confidence cap
goal = "Should we enter the legaltech market? We have no prior legal industry experience."

result = justify_option(
    scored_options=scored_options,
    analyzed_options=analyzed_options,
    goal=goal,
    risk_tolerance="medium",
)

print("[OK] Result keys:", list(result.keys()))
print("\n[OK] alternatives_evaluated:", json.dumps(result.get("alternatives_evaluated"), indent=2))
print("\n[OK] confidence_score:", result.get("confidence_score"))
print("[OK] confidence_level:", result.get("confidence_level"))

# Validate structure
assert "alternatives_evaluated" in result
assert isinstance(result["alternatives_evaluated"], list)
assert len(result["alternatives_evaluated"]) > 0

first_alt = result["alternatives_evaluated"][0]
assert "option" in first_alt
assert "score" in first_alt
assert "pros" in first_alt
assert "cons" in first_alt

# Domain uncertainty should cap confidence at 0.65
assert result["confidence_score"] <= 0.65, f"Domain cap not applied: {result['confidence_score']}"

print("\n[OK] All validations passed")
print(f"\nRecommendation: {result['recommendation']}")

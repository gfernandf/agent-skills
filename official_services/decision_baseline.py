"""
Decision baseline service module.
Provides baseline implementations for decision-domain capabilities.
"""

from __future__ import annotations


def justify_option(scored_options, analyzed_options, goal,
                   tradeoffs=None, constraints=None, risk_tolerance=None):
    """
    Select a recommendation from scored+analyzed options and justify it.

    Baseline heuristic: picks the option with the highest overall_score
    (or the first one if scores are missing) and builds a structured
    justification from the available data.
    """
    risk_tolerance = risk_tolerance or "medium"

    # Pick best option by overall_score
    best = None
    best_score = -1.0
    all_options = scored_options if isinstance(scored_options, list) else []

    for opt in all_options:
        s = opt.get("overall_score", 0.0) if isinstance(opt, dict) else 0.0
        if s > best_score:
            best_score = s
            best = opt

    if best is None and all_options:
        best = all_options[0]

    rec_label = best.get("label", best.get("option_id", "option-1")) if best else "no-option"

    alternatives = []
    for opt in all_options:
        oid = opt.get("option_id", opt.get("id", "?"))
        label = opt.get("label", oid)
        selected = (opt is best)
        alternatives.append({"id": oid, "label": label, "selected": selected})

    confidence = round(min(best_score / 100.0, 1.0), 2) if best_score > 0 else 0.4
    if confidence < 0.35:
        level = "low"
    elif confidence < 0.65:
        level = "medium"
    else:
        level = "high"

    return {
        "recommendation": f"Proceed with {rec_label}.",
        "alternatives_considered": alternatives,
        "confidence_score": confidence,
        "confidence_level": level,
        "uncertainties": ["Baseline analysis — real uncertainties require deeper evaluation."],
        "failure_modes": ["Key assumptions may not hold under changing conditions."],
        "next_steps": ["Validate recommendation with domain experts.", "Run a pilot if feasible."],
        "human_readable": (
            f"Based on the evaluation, the recommended option is '{rec_label}'. "
            f"This selection reflects a {level} confidence level ({confidence}). "
            f"Risk tolerance was set to {risk_tolerance}. "
            f"Next steps include expert validation and a pilot run."
        ),
    }

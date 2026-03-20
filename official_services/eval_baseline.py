"""
Eval baseline service module.
Provides baseline implementations for scoring outputs.
"""

from __future__ import annotations


def score_output(output, rubric=None):
    """
    Compute a lightweight quality score based on rubric dimensions.
    """
    if not isinstance(output, dict):
        return {"score": 0.0, "dimensions": {"valid_output_object": 0.0}}

    dimensions = {}

    if isinstance(rubric, dict) and isinstance(rubric.get("dimensions"), dict):
        for name, weight in rubric["dimensions"].items():
            if isinstance(name, str):
                dimensions[name] = float(weight) if isinstance(weight, (int, float)) else 1.0
    else:
        dimensions = {
            "completeness": 1.0,
            "clarity": 1.0,
            "consistency": 1.0,
        }

    # Baseline heuristic: non-empty output maps to higher score.
    non_empty_ratio = sum(1 for v in output.values() if v not in (None, "", [], {})) / max(len(output), 1)

    weighted_total = 0.0
    total_weight = 0.0
    per_dimension = {}

    for name, weight in dimensions.items():
        dim_score = round(100.0 * non_empty_ratio, 2)
        per_dimension[name] = dim_score
        weighted_total += dim_score * weight
        total_weight += weight

    score = round(weighted_total / total_weight, 2) if total_weight else 0.0
    return {"score": score, "dimensions": per_dimension}


def analyze_options(options, goal, context=None):
    """
    Qualitative analysis: pros, cons, risks, assumptions per option.

    Baseline heuristic: generates one pro, one con, one risk, one assumption
    per option based on the option label/description.
    """
    if not isinstance(options, list):
        options = []

    analyzed = []
    for opt in options:
        oid = opt.get("id", opt.get("option_id", "?")) if isinstance(opt, dict) else "?"
        label = opt.get("label", oid) if isinstance(opt, dict) else str(opt)
        analyzed.append({
            "option_id": oid,
            "pros": [f"{label} addresses the stated goal."],
            "cons": [f"{label} may have hidden costs or complexity."],
            "risks": [{"description": f"Risk associated with {label}.", "severity": "medium"}],
            "assumptions": [f"Assumes {label} is feasible within current constraints."],
        })

    return {
        "analyzed_options": analyzed,
        "analysis_notes": "Baseline qualitative analysis.",
    }


def score_options(options, goal, criteria=None, risk_tolerance=None):
    """
    Multi-criteria scoring of options.

    Baseline heuristic: assigns equal scores to all options based on how many
    fields they have filled in, generates default criteria if none provided.
    """
    if not isinstance(options, list):
        options = []

    if not criteria or not isinstance(criteria, list):
        criteria = [
            {"name": "feasibility", "description": "How feasible is this option?", "weight": 1.0},
            {"name": "impact", "description": "What is the expected impact?", "weight": 1.0},
            {"name": "risk", "description": "What is the risk level?", "weight": 1.0},
        ]

    scored = []
    for opt in options:
        oid = opt.get("id", opt.get("option_id", "?")) if isinstance(opt, dict) else "?"
        label = opt.get("label", oid) if isinstance(opt, dict) else str(opt)
        filled = sum(1 for v in (opt.values() if isinstance(opt, dict) else []) if v) / max(len(opt) if isinstance(opt, dict) else 1, 1)
        base_score = round(filled * 80 + 10, 2)

        per_criterion = {}
        for c in criteria:
            per_criterion[c["name"]] = base_score

        scored.append({
            "option_id": oid,
            "label": label,
            "overall_score": base_score,
            "per_criterion_scores": per_criterion,
            "strengths": [f"{label} has a clear definition."],
            "weaknesses": [f"{label} needs more detailed evaluation."],
        })

    comparative = f"All {len(scored)} options scored on {len(criteria)} criteria."
    tradeoffs_out = [{"tension": "Feasibility vs Impact", "gained": "Lower risk", "lost": "Potentially lower reward"}] if len(scored) > 1 else []

    return {
        "scored_options": scored,
        "criteria_used": criteria,
        "comparative_summary": comparative,
        "tradeoffs": tradeoffs_out,
    }

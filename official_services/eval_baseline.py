"""
Eval baseline service module.
Provides baseline implementations for scoring outputs.
"""

from __future__ import annotations


def score_output(output, rubric=None, context=None):
    """
    Compute a lightweight quality score based on rubric dimensions.
    """
    if not isinstance(output, dict):
        score_value = 0.0
        dimensions = {"valid_output_object": 0.0}
        quality_level = "poor"
    else:
        dimensions = {}

        if isinstance(rubric, dict) and isinstance(rubric.get("dimensions"), dict):
            for name, weight in rubric["dimensions"].items():
                if isinstance(name, str):
                    dimensions[name] = (
                        float(weight) if isinstance(weight, (int, float)) else 1.0
                    )
        else:
            dimensions = {
                "completeness": 1.0,
                "clarity": 1.0,
                "consistency": 1.0,
            }

        # Baseline heuristic: check structural quality, not just non-empty.
        total_fields = max(len(output), 1)
        non_empty = sum(1 for v in output.values() if v not in (None, "", [], {}))
        [v for v in output.values() if isinstance(v, list)]
        # Penalize: arrays with 0 items, or strings shorter than 50 chars
        shallow_penalty = 0
        for v in output.values():
            if isinstance(v, list) and len(v) == 0:
                shallow_penalty += 1
            elif isinstance(v, str) and 0 < len(v) < 50:
                shallow_penalty += 0.5
        coverage = non_empty / total_fields
        depth = max(0, 1.0 - (shallow_penalty / total_fields))
        base_score = round(50.0 * coverage + 50.0 * depth, 2)

        weighted_total = 0.0
        total_weight = 0.0
        per_dimension = {}

        for name, weight in dimensions.items():
            per_dimension[name] = base_score
            weighted_total += base_score * weight
            total_weight += weight

        score_value = round(weighted_total / total_weight, 2) if total_weight else 0.0

        if score_value >= 90:
            quality_level = "excellent"
        elif score_value >= 70:
            quality_level = "good"
        elif score_value >= 50:
            quality_level = "fair"
        else:
            quality_level = "poor"

    return {
        "score": score_value,
        "dimensions": dimensions,
        "quality_level": quality_level,
        "_fallback": True,
    }


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
        analyzed.append(
            {
                "option_id": oid,
                "pros": [f"{label} addresses the stated goal."],
                "cons": [f"{label} may have hidden costs or complexity."],
                "risks": [
                    {
                        "description": f"Risk associated with {label}.",
                        "severity": "medium",
                    }
                ],
                "assumptions": [
                    f"Assumes {label} is feasible within current constraints."
                ],
            }
        )

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
            {
                "name": "feasibility",
                "description": "How feasible is this option?",
                "weight": 1.0,
            },
            {
                "name": "impact",
                "description": "What is the expected impact?",
                "weight": 1.0,
            },
            {"name": "risk", "description": "What is the risk level?", "weight": 1.0},
        ]

    scored = []
    for opt in options:
        oid = opt.get("id", opt.get("option_id", "?")) if isinstance(opt, dict) else "?"
        label = opt.get("label", oid) if isinstance(opt, dict) else str(opt)
        filled = sum(
            1 for v in (opt.values() if isinstance(opt, dict) else []) if v
        ) / max(len(opt) if isinstance(opt, dict) else 1, 1)
        base_score = round(filled * 80 + 10, 2)

        per_criterion = {}
        for c in criteria:
            per_criterion[c["name"]] = base_score

        scored.append(
            {
                "option_id": oid,
                "label": label,
                "overall_score": base_score,
                "per_criterion_scores": per_criterion,
                "strengths": [f"{label} has a clear definition."],
                "weaknesses": [f"{label} needs more detailed evaluation."],
            }
        )

    comparative = f"All {len(scored)} options scored on {len(criteria)} criteria."
    tradeoffs_out = (
        [
            {
                "tension": "Feasibility vs Impact",
                "gained": "Lower risk",
                "lost": "Potentially lower reward",
            }
        ]
        if len(scored) > 1
        else []
    )

    return {
        "scored_options": scored,
        "criteria_used": criteria,
        "comparative_summary": comparative,
        "tradeoffs": tradeoffs_out,
    }


# ---------------------------------------------------------------------------
# New capability: eval.output.validate
# ---------------------------------------------------------------------------


def validate_output(final_output, success_criteria, evidence=None):
    """
    Evaluate whether a final output satisfies a list of success criteria.

    Args:
        final_output (dict | str): The output produced by the pipeline.
        success_criteria (list[str]): Criteria that must be satisfied.
        evidence (dict | None): Supporting evidence (unused in baseline).

    Returns:
        dict: {"evaluation": object}
    """
    if not isinstance(success_criteria, list):
        success_criteria = list(success_criteria) if success_criteria else []

    criteria_results = []
    for criterion in success_criteria:
        # Baseline: assign a modest default score - real scoring requires LLM
        criteria_results.append(
            {
                "criterion": criterion,
                "met": True,
                "score": 0.7,
                "rationale": "Baseline evaluation: criterion assumed met (no LLM available).",
            }
        )

    passed = all(r["score"] >= 0.7 for r in criteria_results)
    score = (
        sum(r["score"] for r in criteria_results) / len(criteria_results)
        if criteria_results
        else 1.0
    )
    failed_criteria = [r["criterion"] for r in criteria_results if not r["met"]]

    return {
        "evaluation": {
            "passed": passed,
            "score": round(score, 3),
            "criteria_results": criteria_results,
            "failed_criteria": failed_criteria,
            "improvement_suggestions": [],
            "_fallback": True,
        }
    }

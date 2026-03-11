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

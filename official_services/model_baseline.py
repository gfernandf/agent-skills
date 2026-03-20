"""
Model baseline service module.
Provides baseline implementations for model-domain capabilities.
"""

from __future__ import annotations


def validate_response(output, validation_policy=None, evidence_context=None):
    """
    Validate a model-generated output for semantic coherence, evidence
    grounding, and structural completeness.

    Baseline heuristic: checks that output is a non-empty dict, flags
    empties, and returns a pass with no issues.
    """
    issues = []
    valid = True

    if not isinstance(output, dict):
        valid = False
        issues.append("Output is not a dict.")
    elif not output:
        valid = False
        issues.append("Output is empty.")
    else:
        for k, v in output.items():
            if v in (None, "", [], {}):
                issues.append(f"Field '{k}' is empty or null.")

    if issues:
        valid = False

    return {
        "valid": valid,
        "issues": issues,
        "confidence_adjustment": 0.0,
        "rationale": "Baseline structural validation." if valid else f"Found {len(issues)} issue(s).",
    }

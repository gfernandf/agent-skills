"""
Policy baseline service module.
Provides baseline implementations for policy and constraint operations.
"""

from __future__ import annotations


def validate_constraint(payload, constraint):
    """
    Validate payload against simple constraint rules.

    Supported baseline rules:
    - required_keys: list[str]
    - forbidden_keys: list[str]
    """
    if not isinstance(payload, dict):
        return {"valid": False, "violations": ["payload_must_be_object"]}
    if not isinstance(constraint, dict):
        return {"valid": False, "violations": ["constraint_must_be_object"]}

    violations = []

    required_keys = constraint.get("required_keys", [])
    if isinstance(required_keys, list):
        for key in required_keys:
            if isinstance(key, str) and key not in payload:
                violations.append(f"missing_required_key:{key}")

    forbidden_keys = constraint.get("forbidden_keys", [])
    if isinstance(forbidden_keys, list):
        for key in forbidden_keys:
            if isinstance(key, str) and key in payload:
                violations.append(f"forbidden_key_present:{key}")

    return {"valid": len(violations) == 0, "violations": violations}


def gate_constraint(payload, gate):
    """
    Evaluate a payload against a policy gate and return pass/block.

    Supported gate rules: required_keys, forbidden_keys, max_size.
    """
    if not isinstance(payload, dict):
        return {
            "decision": "block",
            "violations": ["payload_must_be_object"],
            "rationale": "Payload is not a dict.",
        }
    if not isinstance(gate, dict):
        return {
            "decision": "block",
            "violations": ["gate_must_be_object"],
            "rationale": "Gate definition is not a dict.",
        }

    rules = gate.get("rules", gate)
    action = gate.get("action", "block")
    violations = []

    for key in rules.get("required_keys") or []:
        if isinstance(key, str) and key not in payload:
            violations.append(f"missing_required_key:{key}")

    for key in rules.get("forbidden_keys") or []:
        if isinstance(key, str) and key in payload:
            violations.append(f"forbidden_key_present:{key}")

    max_size = rules.get("max_size")
    if isinstance(max_size, (int, float)):
        import json

        size = len(json.dumps(payload))
        if size > max_size:
            violations.append(f"payload_exceeds_max_size:{size}>{int(max_size)}")

    decision = "pass" if not violations else str(action)
    rationale = (
        "All gate rules satisfied."
        if not violations
        else f"{len(violations)} violation(s) detected."
    )
    return {"decision": decision, "violations": violations, "rationale": rationale}


def justify_decision(decision, rules, context=None):
    """
    Justify a policy decision by linking it to applicable rules.
    """
    rules_list = rules if isinstance(rules, list) else []
    applicable = [
        r for r in rules_list if isinstance(r, dict) and r.get("outcome") == decision
    ]
    if not applicable:
        applicable = rules_list[:1]

    rule_ids = [r.get("id", "unknown") for r in applicable]
    justification = f"Decision '{decision}' is justified by {len(applicable)} applicable rule(s): {', '.join(rule_ids)}."
    confidence = min(len(applicable) / max(len(rules_list), 1), 1.0)

    return {
        "justification": justification,
        "applicable_rules": applicable,
        "confidence": round(confidence, 3),
    }


def classify_risk(action, categories=None):
    """
    Classify the risk level of an action based on heuristic indicators.
    """
    cats = (
        categories
        if isinstance(categories, list) and categories
        else ["low", "medium", "high", "critical"]
    )
    if not isinstance(action, dict):
        return {
            "risk_level": cats[0],
            "factors": [],
            "rationale": "Action is not a dict; defaulting to lowest risk.",
        }

    factors = []
    score = 0

    if action.get("destructive") or action.get("irreversible"):
        factors.append("destructive_or_irreversible")
        score += 2
    if action.get("external") or action.get("public"):
        factors.append("external_exposure")
        score += 1
    if action.get("involves_pii") or action.get("pii"):
        factors.append("pii_involvement")
        score += 1
    if (
        action.get("cost")
        and isinstance(action["cost"], (int, float))
        and action["cost"] > 100
    ):
        factors.append("high_cost")
        score += 1

    idx = min(score, len(cats) - 1)
    risk_level = cats[idx]
    rationale = (
        f"Risk classified as '{risk_level}' based on {len(factors)} factor(s)."
        if factors
        else f"No risk factors detected; classified as '{risk_level}'."
    )

    return {"risk_level": risk_level, "factors": factors, "rationale": rationale}


def score_risk(action, dimensions=None):
    """
    Compute a numeric risk score for an action across policy dimensions.
    """
    dims = (
        dimensions
        if isinstance(dimensions, list) and dimensions
        else [
            "data_exposure",
            "reversibility",
            "blast_radius",
        ]
    )
    if not isinstance(action, dict):
        return {
            "risk_score": 0.0,
            "dimension_scores": {d: 0.0 for d in dims},
            "safe": True,
        }

    dim_scores = {}
    for dim in dims:
        d = str(dim).lower()
        if d in ("data_exposure", "pii"):
            dim_scores[d] = (
                0.7 if action.get("involves_pii") or action.get("pii") else 0.1
            )
        elif d == "reversibility":
            dim_scores[d] = (
                0.8 if action.get("irreversible") or action.get("destructive") else 0.1
            )
        elif d == "blast_radius":
            dim_scores[d] = (
                0.6 if action.get("external") or action.get("public") else 0.2
            )
        else:
            dim_scores[d] = 0.2

    risk_score = round(max(dim_scores.values()) if dim_scores else 0.0, 3)
    return {
        "risk_score": risk_score,
        "dimension_scores": {k: round(v, 3) for k, v in dim_scores.items()},
        "safe": risk_score < 0.5,
    }

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

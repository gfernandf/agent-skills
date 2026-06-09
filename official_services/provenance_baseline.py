"""
Provenance baseline service module.
Provides baseline implementations for citation and claim verification operations.
"""

from __future__ import annotations

from datetime import datetime, timezone


def generate_citation(source, excerpt=None, locator=None):
    """
    Build a structured citation object from a source descriptor.
    """
    if not isinstance(source, dict):
        source = {"raw": str(source)}

    citation = {
        "source": source,
        "excerpt": excerpt if isinstance(excerpt, str) else None,
        "locator": locator if isinstance(locator, str) else None,
    }
    return {"citation": citation}


def verify_claim(claim, sources):
    """
    Verify claim support by checking token overlap against source text fields.
    """
    if not isinstance(claim, str) or not claim.strip():
        return {
            "verified": False,
            "evidence": [],
            "rationale": "claim_is_empty",
        }

    if not isinstance(sources, list):
        return {
            "verified": False,
            "evidence": [],
            "rationale": "sources_must_be_array",
        }

    claim_tokens = {t.lower() for t in claim.split() if t.strip()}
    evidence = []

    for idx, source in enumerate(sources):
        if isinstance(source, dict):
            text = source.get("text")
            if isinstance(text, str):
                source_tokens = {t.lower() for t in text.split() if t.strip()}
                overlap = claim_tokens.intersection(source_tokens)
                if overlap:
                    evidence.append(
                        {
                            "source_index": idx,
                            "matched_tokens": sorted(overlap),
                        }
                    )

    verified = len(evidence) > 0
    rationale = "token_overlap_found" if verified else "no_supporting_overlap"

    return {
        "verified": verified,
        "evidence": evidence,
        "rationale": rationale,
    }


def store_decision(
    decision_id,
    principal,
    action,
    decision,
    resource=None,
    policy_refs=None,
    evidence=None,
):
    principal_obj = principal if isinstance(principal, dict) else {}
    action_obj = action if isinstance(action, dict) else {}
    decision_obj = decision if isinstance(decision, dict) else {}

    normalized_decision_id = str(decision_id or "decision-unknown")
    principal_id = str(principal_obj.get("id") or "principal-unknown")
    action_type = str(action_obj.get("type") or "unspecified")
    outcome = str(
        decision_obj.get("outcome") or decision_obj.get("decision") or "unknown"
    )

    record_id = f"audit-{normalized_decision_id}-{principal_id}"
    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    stored_evidence = evidence if isinstance(evidence, dict) else {}

    return {
        "recorded": True,
        "record_id": record_id,
        "timestamp": timestamp,
        "evidence": {
            **stored_evidence,
            "principal": principal_obj,
            "action": action_obj,
            "resource": resource if isinstance(resource, dict) else None,
            "policy_refs": policy_refs if isinstance(policy_refs, list) else [],
        },
        "rationale": (
            "Decision stored for auditability: "
            f"decision_id={normalized_decision_id}, outcome={outcome}, action={action_type}."
        ),
    }

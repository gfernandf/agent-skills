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


def generate_governance_citation(source, excerpt=None, locator=None):
    citation_payload = generate_citation(
        source=source, excerpt=excerpt, locator=locator
    )
    citation = (
        citation_payload.get("citation") if isinstance(citation_payload, dict) else {}
    )

    source_obj = source if isinstance(source, dict) else {"raw": str(source)}
    trace_ref = source_obj.get("trace_ref") or source_obj.get("id")
    if trace_ref is not None:
        trace_ref = str(trace_ref)

    return {
        "citation": citation,
        "status": "ok",
        "trace_ref": trace_ref,
        "evidence": {
            "source_fields": sorted(list(source_obj.keys())),
            "has_excerpt": isinstance(excerpt, str) and bool(excerpt.strip()),
            "has_locator": isinstance(locator, str) and bool(locator.strip()),
        },
        "rationale": "Citation generated from normalized source fields.",
    }


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


def summarize_trace(execution_trace):
    trace = execution_trace if isinstance(execution_trace, dict) else {}
    step_results = (
        trace.get("step_results") if isinstance(trace.get("step_results"), list) else []
    )

    total_steps = len(step_results)
    failed_steps = sum(
        1
        for step in step_results
        if isinstance(step, dict)
        and str(step.get("status", "")).lower() in {"failed", "error"}
    )

    overall_status = str(trace.get("status") or "unknown")
    if failed_steps > 0:
        status = "partial"
    elif overall_status in {"success", "ok", "completed"}:
        status = "ok"
    else:
        status = "partial"

    trace_ref = trace.get("trace_ref") or trace.get("run_id")
    if trace_ref is not None:
        trace_ref = str(trace_ref)

    return {
        "trace_summary": {
            "overall_status": overall_status,
            "total_steps": total_steps,
            "failed_steps": failed_steps,
            "successful_steps": max(0, total_steps - failed_steps),
        },
        "status": status,
        "trace_ref": trace_ref,
        "evidence": {
            "observed_step_statuses": [
                str(step.get("status", "unknown"))
                for step in step_results
                if isinstance(step, dict)
            ]
        },
        "rationale": "Trace summary generated from execution status and step outcomes.",
    }

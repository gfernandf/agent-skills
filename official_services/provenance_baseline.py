"""
Provenance baseline service module.
Provides baseline implementations for citation and claim verification operations.
"""

from __future__ import annotations


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
                    evidence.append({
                        "source_index": idx,
                        "matched_tokens": sorted(overlap),
                    })

    verified = len(evidence) > 0
    rationale = "token_overlap_found" if verified else "no_supporting_overlap"

    return {
        "verified": verified,
        "evidence": evidence,
        "rationale": rationale,
    }

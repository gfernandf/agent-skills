"""
Security baseline service module.
Provides baseline implementations for PII/secret detection and output gating.
"""

from __future__ import annotations

import re


_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"\b\+?\d[\d\s\-]{7,}\d\b")
_SECRET_RE = re.compile(
    r"\b(?:sk-[A-Za-z0-9]{16,}|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{20,})\b"
)


def detect_pii(text):
    if not isinstance(text, str):
        return {"contains_pii": False, "findings": []}

    findings = []
    for match in _EMAIL_RE.finditer(text):
        findings.append({"type": "email", "value": match.group(0)})
    for match in _PHONE_RE.finditer(text):
        findings.append({"type": "phone", "value": match.group(0)})

    return {"contains_pii": len(findings) > 0, "findings": findings}


def redact_pii(text):
    if not isinstance(text, str):
        return {"redacted_text": "", "findings": []}

    findings = []

    def _mask_email(m):
        findings.append({"type": "email", "value": m.group(0)})
        return "REDACTED_EMAIL"

    def _mask_phone(m):
        findings.append({"type": "phone", "value": m.group(0)})
        return "REDACTED_PHONE"

    redacted = _EMAIL_RE.sub(_mask_email, text)
    redacted = _PHONE_RE.sub(_mask_phone, redacted)

    return {"redacted_text": redacted, "findings": findings}


def detect_secret(text):
    if not isinstance(text, str):
        return {"contains_secret": False, "findings": []}

    findings = [
        {"type": "secret_token", "value": m.group(0)} for m in _SECRET_RE.finditer(text)
    ]
    return {"contains_secret": len(findings) > 0, "findings": findings}


def classify_content(payload, context=None):
    """Classify sensitive content categories in a payload."""
    ctx = context if isinstance(context, dict) else {}
    data = payload if isinstance(payload, dict) else {"text": payload}

    text = " ".join(
        str(part)
        for part in [
            data.get("text", ""),
            data.get("content", ""),
            data.get("body", ""),
        ]
        if part is not None
    ).lower()
    labels = data.get("labels") if isinstance(data.get("labels"), list) else []
    label_text = " ".join(str(label).lower() for label in labels)
    haystack = f"{text} {label_text} {ctx}".lower()

    categories = []
    scores = {}
    detectors = {
        "pii": ["@", "ssn", "social security", "phone", "customer", "email"],
        "phi": ["patient", "diagnosis", "medical", "health"],
        "financial": ["invoice", "account number", "bank", "payment", "refund", "card"],
        "legal": ["contract", "nda", "attorney", "privileged", "case"],
        "credentials": [
            "password",
            "api key",
            "secret",
            "token",
            "credential",
            "bearer",
        ],
        "source_code": ["def ", "class ", "import ", "function", "{", "}"],
    }

    for category, hints in detectors.items():
        hit = any(hint in haystack for hint in hints)
        if hit:
            categories.append(category)
            scores[category] = (
                0.85 if category in {"credentials", "pii", "financial"} else 0.65
            )

    if not categories and labels:
        for label in labels:
            normalized = str(label).lower()
            if normalized in detectors:
                categories.append(normalized)
                scores[normalized] = 0.6

    severity = len(categories) + (1 if ctx.get("external") else 0)
    if severity >= 4:
        sensitivity_level = "critical"
    elif severity >= 2:
        sensitivity_level = "high"
    elif severity == 1:
        sensitivity_level = "medium"
    else:
        sensitivity_level = "low"

    rationale = (
        f"Detected categories: {', '.join(categories)}."
        if categories
        else "No sensitive categories detected."
    )
    evidence = {"labels": labels, "signals": categories, "context": ctx}

    return {
        "categories": categories,
        "sensitivity_level": sensitivity_level,
        "category_scores": scores,
        "rationale": rationale,
        "evidence": evidence,
    }


def gate_output(output, policy):
    if not isinstance(output, dict):
        return {"allowed": False, "reasons": ["output_must_be_object"]}
    if not isinstance(policy, dict):
        return {"allowed": False, "reasons": ["policy_must_be_object"]}

    reasons = []
    text = str(output)

    if policy.get("block_pii"):
        pii = detect_pii(text)
        if pii.get("contains_pii"):
            reasons.append("pii_detected")

    if policy.get("block_secrets"):
        sec = detect_secret(text)
        if sec.get("contains_secret"):
            reasons.append("secret_detected")

    return {"allowed": len(reasons) == 0, "reasons": reasons}

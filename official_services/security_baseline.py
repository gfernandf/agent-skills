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

"""
Model baseline service module.
Provides baseline implementations for model-domain capabilities.
"""

from __future__ import annotations

import hashlib
import re
import struct


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


def generate_embedding(text, model=None, dimensions=None):
    """
    Generate a vector embedding for a text input.

    Baseline: deterministic hash-based pseudo-embedding. Produces a
    fixed-length float vector derived from the SHA-256 digest.  Useful
    for pipeline testing but unsuitable for real semantic similarity.
    """
    dim = dimensions if isinstance(dimensions, int) and dimensions > 0 else 128
    text_str = str(text) if text else ""

    digest = hashlib.sha256(text_str.encode("utf-8")).digest()
    # Extend the digest to cover the requested dimensions
    extended = digest
    while len(extended) < dim * 4:
        extended += hashlib.sha256(extended).digest()

    floats = list(struct.unpack(f"<{dim}f", extended[: dim * 4]))
    # Normalize to unit-length
    norm = sum(f * f for f in floats) ** 0.5
    if norm > 0:
        floats = [f / norm for f in floats]

    return {
        "embedding": floats,
        "model": model or "baseline-hash",
    }


def classify_output(output, categories, context=None):
    """
    Classify a model-generated output into one of the provided categories.

    Baseline heuristic: inspects the output structure and content to pick
    the best-matching category using simple keyword/pattern matching.
    """
    if not isinstance(categories, list) or not categories:
        return {"category": "unknown", "confidence": 0.0, "rationale": "No categories provided."}

    text = _flatten_to_text(output)
    lower = text.lower()

    # Simple heuristic scoring
    scores: dict[str, float] = {}
    for cat in categories:
        cat_str = str(cat).lower()
        count = lower.count(cat_str)
        scores[cat_str] = count

    # Structural heuristics
    if isinstance(output, dict):
        if any(k in output for k in ("code", "snippet", "source")):
            scores["code"] = scores.get("code", 0) + 3
        if any(k in output for k in ("items", "list", "rows")):
            scores["list"] = scores.get("list", 0) + 3
        if any(k in output for k in ("summary", "abstract", "overview")):
            scores["summary"] = scores.get("summary", 0) + 3
        if any(k in output for k in ("error", "exception", "traceback")):
            scores["error"] = scores.get("error", 0) + 3

    # Match scored keys back to original category labels
    best_cat = categories[0]
    best_score = 0.0
    for cat in categories:
        s = scores.get(str(cat).lower(), 0)
        if s > best_score:
            best_score = s
            best_cat = cat

    confidence = min(best_score / 5.0, 1.0) if best_score > 0 else 1.0 / len(categories)

    return {
        "category": str(best_cat),
        "confidence": round(confidence, 3),
        "rationale": "Baseline keyword/structure heuristic.",
    }


def score_output(output, instruction, reference=None, dimensions=None):
    """
    Score a model-generated output on quality dimensions.

    Baseline heuristic: uses structural checks (length, field count,
    non-empty ratio) to produce rough scores.  Not a substitute for
    LLM-based evaluation.
    """
    dims = dimensions if isinstance(dimensions, list) and dimensions else [
        "relevance", "fluency", "completeness", "faithfulness",
    ]

    text = _flatten_to_text(output)
    instr_text = str(instruction) if instruction else ""
    word_count = len(text.split())

    dim_scores: dict[str, float] = {}
    for dim in dims:
        dim_str = str(dim).lower()
        if dim_str == "relevance":
            # Overlap between instruction keywords and output
            instr_words = set(instr_text.lower().split())
            out_words = set(text.lower().split())
            overlap = len(instr_words & out_words)
            dim_scores[dim_str] = min(overlap / max(len(instr_words), 1), 1.0)
        elif dim_str == "fluency":
            # Rough proxy: average sentence length is reasonable
            sentences = [s.strip() for s in re.split(r'[.!?]+', text) if s.strip()]
            avg_len = sum(len(s.split()) for s in sentences) / max(len(sentences), 1)
            dim_scores[dim_str] = min(avg_len / 20.0, 1.0) if avg_len > 2 else 0.3
        elif dim_str == "completeness":
            # Proxy: output word count relative to instruction length
            expected = max(len(instr_text.split()) * 2, 10)
            dim_scores[dim_str] = min(word_count / expected, 1.0)
        elif dim_str == "faithfulness":
            # Without reference, assume moderate faithfulness
            if reference:
                ref_text = _flatten_to_text(reference)
                ref_words = set(ref_text.lower().split())
                out_words = set(text.lower().split())
                overlap = len(ref_words & out_words)
                dim_scores[dim_str] = min(overlap / max(len(ref_words), 1), 1.0)
            else:
                dim_scores[dim_str] = 0.5
        else:
            dim_scores[dim_str] = 0.5

    dim_scores = {k: round(v, 3) for k, v in dim_scores.items()}
    overall = round(sum(dim_scores.values()) / max(len(dim_scores), 1), 3)

    return {
        "scores": dim_scores,
        "overall": overall,
        "rationale": "Baseline structural scoring heuristic.",
    }


def sanitize_output(output, policy=None):
    """
    Sanitize a model-generated output by removing PII, harmful patterns,
    and prompt leakage.

    Baseline: regex-based pattern matching for common PII formats and
    known harmful patterns.
    """
    pol = policy if isinstance(policy, dict) else {}
    remove_pii = pol.get("remove_pii", True)
    remove_harmful = pol.get("remove_harmful", True)
    remove_prompt_leakage = pol.get("remove_prompt_leakage", True)

    removals: list[dict] = []
    sanitized = _deep_sanitize(
        output,
        removals=removals,
        remove_pii=remove_pii,
        remove_harmful=remove_harmful,
        remove_prompt_leakage=remove_prompt_leakage,
    )

    return {
        "sanitized_output": sanitized,
        "removals": removals,
        "clean": len(removals) == 0,
    }


def template_prompt(template, variables, format=None):
    """
    Render a model prompt from a template and variable bindings.

    Supports ${variable} placeholder syntax.  Unresolved placeholders
    are left in place and reported in the unresolved list.
    """
    template_str = str(template) if template else ""
    vars_map = variables if isinstance(variables, dict) else {}

    unresolved: list[str] = []

    def _replace(match):
        key = match.group(1)
        if key in vars_map:
            return str(vars_map[key])
        unresolved.append(key)
        return match.group(0)

    prompt = re.sub(r'\$\{(\w+(?:\.\w+)*)}', _replace, template_str)

    return {
        "prompt": prompt,
        "unresolved": unresolved,
    }


def score_risk(output, context=None, dimensions=None):
    """
    Assess risk level of a model-generated output across safety dimensions.

    Baseline: keyword and pattern-based risk scoring.  Checks for known
    harmful patterns, potential PII leakage, and prompt injection markers.
    """
    dims = dimensions if isinstance(dimensions, list) and dimensions else [
        "toxicity", "bias", "hallucination", "prompt_injection",
    ]

    text = _flatten_to_text(output)
    lower = text.lower()
    context_text = str(context).lower() if context else ""

    dim_scores: dict[str, float] = {}
    flags: list[dict] = []

    for dim in dims:
        dim_str = str(dim).lower()
        score = 0.0

        if dim_str == "toxicity":
            toxic_patterns = [
                r'\b(kill|murder|attack|destroy|hate|die)\b',
                r'\b(stupid|idiot|dumb|moron)\b',
            ]
            for pat in toxic_patterns:
                hits = len(re.findall(pat, lower))
                score += hits * 0.15
            score = min(score, 1.0)

        elif dim_str == "bias":
            bias_patterns = [
                r'\b(always|never|every|all)\s+(men|women|people|group)',
                r'\b(obviously|clearly|everyone knows)\b',
            ]
            for pat in bias_patterns:
                hits = len(re.findall(pat, lower))
                score += hits * 0.2
            score = min(score, 1.0)

        elif dim_str == "hallucination":
            # Heuristic: if context is provided, check for claims not in context
            if context_text:
                out_words = set(lower.split()) - {"the", "a", "an", "is", "are", "was", "were", "in", "on", "at", "to", "for", "of", "and", "or"}
                ctx_words = set(context_text.split())
                novel = out_words - ctx_words
                ratio = len(novel) / max(len(out_words), 1)
                score = min(ratio, 1.0)
            else:
                score = 0.3  # moderate uncertainty without context

        elif dim_str == "prompt_injection":
            injection_patterns = [
                r'ignore\s+(previous|above|all)\s+(instructions?|prompts?)',
                r'you\s+are\s+now\s+',
                r'system\s*:\s*',
                r'<\|?(?:system|im_start)\|?>',
            ]
            for pat in injection_patterns:
                if re.search(pat, lower):
                    score = max(score, 0.8)
                    flags.append({"dimension": dim_str, "detail": f"Pattern matched: {pat}"})

        else:
            score = 0.1

        dim_scores[dim_str] = round(score, 3)
        if score >= 0.5 and dim_str != "prompt_injection":
            flags.append({"dimension": dim_str, "detail": f"Score {score:.2f} above threshold."})

    dim_scores = {k: round(v, 3) for k, v in dim_scores.items()}
    risk_score = round(max(dim_scores.values()) if dim_scores else 0.0, 3)

    return {
        "risk_score": risk_score,
        "dimension_scores": dim_scores,
        "flags": flags,
        "safe": risk_score < 0.5,
    }


# ── Internal helpers ──


_PII_PATTERNS = [
    (r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', "email"),
    (r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b', "phone_us"),
    (r'\b\d{3}-\d{2}-\d{4}\b', "ssn"),
    (r'\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b', "credit_card"),
]

_HARMFUL_PATTERNS = [
    r'(?i)\b(?:password|passwd|secret_?key|api_?key)\s*[:=]\s*\S+',
]

_LEAKAGE_PATTERNS = [
    r'(?i)(?:system prompt|you are a|your instructions are)',
    r'(?i)<\|?(?:system|im_start)\|?>',
]


def _deep_sanitize(obj, *, removals, remove_pii, remove_harmful, remove_prompt_leakage, path=""):
    """Recursively sanitize strings inside any nested structure."""
    if isinstance(obj, str):
        return _sanitize_string(
            obj, removals=removals, path=path,
            remove_pii=remove_pii, remove_harmful=remove_harmful,
            remove_prompt_leakage=remove_prompt_leakage,
        )
    if isinstance(obj, dict):
        return {
            k: _deep_sanitize(
                v, removals=removals, path=f"{path}.{k}" if path else k,
                remove_pii=remove_pii, remove_harmful=remove_harmful,
                remove_prompt_leakage=remove_prompt_leakage,
            )
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [
            _deep_sanitize(
                item, removals=removals, path=f"{path}[{i}]",
                remove_pii=remove_pii, remove_harmful=remove_harmful,
                remove_prompt_leakage=remove_prompt_leakage,
            )
            for i, item in enumerate(obj)
        ]
    return obj


def _sanitize_string(text, *, removals, path, remove_pii, remove_harmful, remove_prompt_leakage):
    """Apply regex-based sanitization to a single string."""
    result = text

    if remove_pii:
        for pattern, label in _PII_PATTERNS:
            matches = re.findall(pattern, result)
            if matches:
                result = re.sub(pattern, "[REDACTED]", result)
                removals.append({"field": path, "pattern": label, "action": "redacted"})

    if remove_harmful:
        for pattern in _HARMFUL_PATTERNS:
            if re.search(pattern, result):
                result = re.sub(pattern, "[REMOVED]", result)
                removals.append({"field": path, "pattern": "harmful_content", "action": "removed"})

    if remove_prompt_leakage:
        for pattern in _LEAKAGE_PATTERNS:
            if re.search(pattern, result):
                result = re.sub(pattern, "[FILTERED]", result)
                removals.append({"field": path, "pattern": "prompt_leakage", "action": "filtered"})

    return result


def _flatten_to_text(obj) -> str:
    """Recursively extract all string content from a nested structure."""
    if isinstance(obj, str):
        return obj
    if isinstance(obj, dict):
        return " ".join(_flatten_to_text(v) for v in obj.values())
    if isinstance(obj, (list, tuple)):
        return " ".join(_flatten_to_text(item) for item in obj)
    return str(obj) if obj is not None else ""

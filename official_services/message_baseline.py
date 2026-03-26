"""
Message baseline service module.
Provides baseline implementations for message-related capabilities.
"""


def send_message(channel, message):
    """
    Send a message to a channel.

    Args:
        channel (str): The channel identifier.
        message (str): The message content.

    Returns:
        dict: {"sent": bool}
    """
    # Baseline implementation: always succeed
    return {"sent": True}


def classify_priority(message, sender=None, context=None):
    """
    Classify message priority based on content keywords and sender hints.

    Baseline: keyword-based heuristic.
    """
    import re

    text = str(message).lower() if message else ""
    score = 0

    critical_patterns = [r"\b(outage|down|incident|breach|critical)\b"]
    high_patterns = [r"\b(urgent|asap|blocker|escalat|immediate)\b"]
    medium_patterns = [r"\b(important|deadline|review|action required)\b"]

    for pat in critical_patterns:
        if re.search(pat, text):
            score += 3
    for pat in high_patterns:
        if re.search(pat, text):
            score += 2
    for pat in medium_patterns:
        if re.search(pat, text):
            score += 1

    if score >= 3:
        priority = "critical"
    elif score >= 2:
        priority = "high"
    elif score >= 1:
        priority = "medium"
    else:
        priority = "low"

    confidence = min(score / 4.0, 1.0) if score > 0 else 0.6
    rationale = (
        f"Keyword heuristic scored {score} indicator(s)."
        if score > 0
        else "No priority indicators detected; defaulting to low."
    )

    return {
        "priority": priority,
        "confidence": round(confidence, 3),
        "rationale": rationale,
    }

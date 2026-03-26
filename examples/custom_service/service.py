"""Simple keyword-based sentiment analysis — no external deps."""

from __future__ import annotations

_POSITIVE = frozenset(
    {
        "love",
        "great",
        "excellent",
        "amazing",
        "wonderful",
        "fantastic",
        "good",
        "happy",
        "best",
        "awesome",
        "enjoy",
        "perfect",
        "beautiful",
        "like",
        "nice",
        "brilliant",
        "outstanding",
        "superb",
        "delightful",
    }
)
_NEGATIVE = frozenset(
    {
        "hate",
        "terrible",
        "awful",
        "bad",
        "worst",
        "horrible",
        "ugly",
        "poor",
        "disgusting",
        "boring",
        "disappointing",
        "wrong",
        "sad",
        "fail",
        "broken",
        "useless",
        "annoying",
        "dreadful",
        "miserable",
    }
)


def analyze_sentiment(text: str) -> dict:
    """Return ``{sentiment, confidence}`` for the given text."""
    words = set(text.lower().split())
    pos = len(words & _POSITIVE)
    neg = len(words & _NEGATIVE)
    total = pos + neg

    if total == 0:
        return {"sentiment": "neutral", "confidence": 0.5}

    ratio = pos / total
    if ratio > 0.6:
        return {"sentiment": "positive", "confidence": round(ratio, 2)}
    if ratio < 0.4:
        return {"sentiment": "negative", "confidence": round(1 - ratio, 2)}
    return {"sentiment": "neutral", "confidence": 0.5}

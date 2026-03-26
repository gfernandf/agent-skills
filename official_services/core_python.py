from __future__ import annotations

import re
from typing import Any


def summarize_text(text: str, max_length: int | None = None) -> dict[str, Any]:
    """
    Deterministic local implementation for the capability `text.content.summarize`.

    v1 behavior:
    - normalize whitespace
    - trim leading/trailing spaces
    - optionally truncate to max_length
    - if max_length is not provided, return the normalized text as-is
    """
    if not isinstance(text, str):
        raise TypeError("text must be a string")

    if max_length is not None:
        if not isinstance(max_length, int):
            raise TypeError("max_length must be an integer if provided")
        if max_length < 0:
            raise ValueError("max_length must be non-negative")

    normalized = _normalize_text(text)

    if max_length is None:
        return {"summary": normalized}

    if len(normalized) <= max_length:
        return {"summary": normalized}

    if max_length == 0:
        return {"summary": ""}

    truncated = normalized[:max_length].rstrip()

    return {"summary": truncated}


def _normalize_text(text: str) -> str:
    """
    Collapse repeated whitespace into single spaces.
    """
    return re.sub(r"\s+", " ", text).strip()

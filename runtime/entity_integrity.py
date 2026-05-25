"""Utilities to preserve explicit entity contracts across multi-step pipelines."""

from __future__ import annotations

from typing import Any


def _as_text(value: Any, fallback: str) -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    return text or fallback


def normalize_explicit_options(options: Any) -> list[dict[str, Any]]:
    """Normalize explicit options to stable id/label tuples preserving input order."""
    if not isinstance(options, list):
        return []

    normalized: list[dict[str, Any]] = []
    for idx, raw in enumerate(options):
        if isinstance(raw, dict):
            option_id = _as_text(
                raw.get("id", raw.get("option_id")), f"option-{idx + 1}"
            )
            label = _as_text(raw.get("label"), option_id)
            normalized.append(
                {
                    "id": option_id,
                    "label": label,
                    "description": raw.get("description"),
                }
            )
            continue

        option_id = f"option-{idx + 1}"
        label = _as_text(raw, option_id)
        normalized.append({"id": option_id, "label": label, "description": None})

    return normalized


def _index_by_id(options: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for option in options:
        option_id = _as_text(option.get("id"), "")
        if option_id:
            indexed[option_id] = option
    return indexed


def detect_option_drift(
    expected_options: Any,
    observed_options: Any,
) -> dict[str, Any]:
    """Detect additions, omissions, and label drift for option entities."""
    expected = normalize_explicit_options(expected_options)
    observed = normalize_explicit_options(observed_options)

    expected_by_id = _index_by_id(expected)
    observed_by_id = _index_by_id(observed)

    expected_ids = set(expected_by_id)
    observed_ids = set(observed_by_id)

    missing_ids = sorted(expected_ids - observed_ids)
    new_ids = sorted(observed_ids - expected_ids)

    renamed: list[dict[str, str]] = []
    for option_id in sorted(expected_ids & observed_ids):
        expected_label = _as_text(expected_by_id[option_id].get("label"), option_id)
        observed_label = _as_text(observed_by_id[option_id].get("label"), option_id)
        if expected_label != observed_label:
            renamed.append(
                {
                    "id": option_id,
                    "expected_label": expected_label,
                    "observed_label": observed_label,
                }
            )

    has_drift = bool(missing_ids or new_ids or renamed)
    return {
        "has_drift": has_drift,
        "missing_ids": missing_ids,
        "new_ids": new_ids,
        "renamed": renamed,
        "expected_count": len(expected),
        "observed_count": len(observed),
    }


def strict_option_mode(option_constraint_mode: Any, explicit_options: Any) -> bool:
    """Resolve strict mode from explicit override or presence of explicit options."""
    if isinstance(option_constraint_mode, str):
        mode = option_constraint_mode.strip().lower()
        if mode in {"strict", "preserve"}:
            return True
        if mode in {"best_effort", "off", "disabled"}:
            return False
    return bool(normalize_explicit_options(explicit_options))

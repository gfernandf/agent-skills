#!/usr/bin/env python3
"""G4 — Atomic-properties consistency tests.

For each capability that declares a ``properties`` block, verify:

1. Deterministic capabilities must be marked ``idempotent: true``.
2. Capabilities with ``side_effects: true`` must have a ``safety`` block.
3. Capabilities with ``side_effects: false`` must NOT require confirmation.
4. ``idempotent`` is declared (not omitted) when ``deterministic`` is declared.

Run:
    pytest test_atomic_properties.py -v
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import pytest
import yaml

REGISTRY_ROOT = Path(__file__).resolve().parent.parent / "agent-skill-registry"
CAPABILITIES_DIR = REGISTRY_ROOT / "capabilities"


def _load_yaml(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as fh:
        return yaml.safe_load(fh) or {}


def _capabilities_with_properties():
    """Yield (cap_id, data) for capabilities that have a ``properties`` block."""
    if not CAPABILITIES_DIR.exists():
        return
    for p in sorted(CAPABILITIES_DIR.glob("*.yaml")):
        if p.name.startswith("_"):
            continue
        data = _load_yaml(p)
        props = data.get("properties")
        if isinstance(props, dict):
            cid = data.get("id", p.stem)
            yield pytest.param(cid, data, id=cid)


@pytest.mark.parametrize("cap_id,data", list(_capabilities_with_properties()))
class TestAtomicProperties:

    def test_deterministic_implies_idempotent(self, cap_id: str, data: dict):
        props = data["properties"]
        if props.get("deterministic") is True:
            assert props.get("idempotent") is True, (
                f"{cap_id}: deterministic=true but idempotent is not true"
            )

    def test_side_effects_require_safety(self, cap_id: str, data: dict):
        props = data["properties"]
        if props.get("side_effects") is True:
            assert data.get("safety") is not None, (
                f"{cap_id}: side_effects=true but no safety block declared"
            )

    def test_no_side_effects_no_confirmation(self, cap_id: str, data: dict):
        props = data["properties"]
        safety = data.get("safety")
        if props.get("side_effects") is False and isinstance(safety, dict):
            assert safety.get("requires_confirmation") is not True, (
                f"{cap_id}: side_effects=false but requires_confirmation=true"
            )

    def test_deterministic_has_idempotent_declared(self, cap_id: str, data: dict):
        props = data["properties"]
        if "deterministic" in props:
            assert "idempotent" in props, (
                f"{cap_id}: 'deterministic' is declared but 'idempotent' is missing"
            )

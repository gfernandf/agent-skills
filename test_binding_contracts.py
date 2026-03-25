#!/usr/bin/env python3
"""T3 — Binding contract tests.

For every binding YAML under bindings/official/, verify:
1. The referenced capability exists in the registry.
2. Every *required* capability input has an ``input.*`` mapping in the binding request template.
3. Every *required* capability output has a ``response.*`` mapping in the binding response template.
4. No binding request references an input that does not exist in the capability.
"""
from __future__ import annotations

import itertools
from pathlib import Path
from typing import Any, Dict, Set

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent
REGISTRY_ROOT = REPO_ROOT.parent / "agent-skill-registry"
BINDINGS_DIR = REPO_ROOT / "bindings" / "official"
CAPABILITIES_DIR = REGISTRY_ROOT / "capabilities"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_yaml(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as fh:
        return yaml.safe_load(fh) or {}


def _load_capabilities() -> Dict[str, Dict[str, Any]]:
    caps: Dict[str, Dict[str, Any]] = {}
    if not CAPABILITIES_DIR.exists():
        return caps
    for p in CAPABILITIES_DIR.glob("*.yaml"):
        if p.name.startswith("_"):
            continue
        data = _load_yaml(p)
        cid = data.get("id")
        if cid:
            caps[cid] = data
    return caps


def _collect_input_refs(template: Any, refs: Set[str]) -> None:
    """Recursively collect ``input.<field>`` references from a request template."""
    if isinstance(template, str):
        # Handles both direct "input.x" and template vars "${input.x}"
        import re
        for m in re.finditer(r"(?:\$\{)?input\.([A-Za-z_][A-Za-z0-9_]*)(?:\})?", template):
            refs.add(m.group(1))
    elif isinstance(template, dict):
        for v in template.values():
            _collect_input_refs(v, refs)
    elif isinstance(template, list):
        for item in template:
            _collect_input_refs(item, refs)


def _collect_response_refs(template: Any, refs: Set[str]) -> None:
    """Collect the binding-level output field names (keys of the response map)."""
    if isinstance(template, dict):
        refs.update(template.keys())


# ---------------------------------------------------------------------------
# Discover bindings
# ---------------------------------------------------------------------------


def _discover_bindings():
    """Yield (binding_path, binding_data) for every YAML in bindings/official/."""
    if not BINDINGS_DIR.exists():
        return
    for p in sorted(BINDINGS_DIR.rglob("*.yaml")):
        yield p, _load_yaml(p)


_CAPABILITIES = _load_capabilities()


def _binding_ids():
    """Return list of (test_id, binding_path, binding_data) for parametrize."""
    items = []
    for path, data in _discover_bindings():
        bid = data.get("id", path.stem)
        items.append(pytest.param(path, data, id=bid))
    return items


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path,data", _binding_ids())
class TestBindingContract:
    """Validate each binding against its declared capability contract."""

    def test_capability_exists(self, path: Path, data: dict):
        cap_id = data.get("capability")
        assert cap_id, f"{path.name}: missing 'capability' field"
        assert cap_id in _CAPABILITIES, (
            f"{path.name}: capability '{cap_id}' not found in registry"
        )

    def test_required_inputs_covered(self, path: Path, data: dict):
        cap = _CAPABILITIES.get(data.get("capability", ""))
        if cap is None:
            pytest.skip("capability not found")
        cap_inputs = cap.get("inputs", {})
        required = {k for k, v in cap_inputs.items() if isinstance(v, dict) and v.get("required")}
        if not required:
            return

        refs: Set[str] = set()
        _collect_input_refs(data.get("request", {}), refs)
        missing = required - refs
        assert not missing, (
            f"{path.name}: required inputs not mapped in request template: {sorted(missing)}"
        )

    def test_required_outputs_covered(self, path: Path, data: dict):
        cap = _CAPABILITIES.get(data.get("capability", ""))
        if cap is None:
            pytest.skip("capability not found")
        cap_outputs = cap.get("outputs", {})
        required_out = {k for k, v in cap_outputs.items() if isinstance(v, dict) and v.get("required")}
        if not required_out:
            return

        resp_keys: Set[str] = set()
        _collect_response_refs(data.get("response", {}), resp_keys)
        missing = required_out - resp_keys
        assert not missing, (
            f"{path.name}: required outputs not mapped in response template: {sorted(missing)}"
        )

    def test_no_phantom_input_refs(self, path: Path, data: dict):
        cap = _CAPABILITIES.get(data.get("capability", ""))
        if cap is None:
            pytest.skip("capability not found")
        cap_input_names = set(cap.get("inputs", {}).keys())

        refs: Set[str] = set()
        _collect_input_refs(data.get("request", {}), refs)
        phantom = refs - cap_input_names
        assert not phantom, (
            f"{path.name}: binding references inputs not declared in capability: {sorted(phantom)}"
        )

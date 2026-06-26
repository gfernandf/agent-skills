#!/usr/bin/env python3

from __future__ import annotations

import ast
import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parent.parent
REGISTRY_ROOT = ROOT.parent / "agent-skill-registry"
CAPABILITIES_DIR = REGISTRY_ROOT / "capabilities"
BINDINGS_DIR = ROOT / "bindings" / "official"
SMOKE_LIST_PATH = ROOT / "tooling" / "smoke_capabilities.json"
DEFAULT_SELECTION_PATH = ROOT / "policies" / "official_default_selection.yaml"
GOVERNANCE_TOOLS_PATH = ROOT / "official_mcp_servers" / "governance_tools.py"
ACTIVE_BINDINGS_PATH = ROOT / ".agent-skills" / "active_bindings.json"
DEPRECATED_MANIFEST_GLOB = "deprecated_noncanonical_bindings_*.tsv"


def _load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8-sig") as fh:
        data = yaml.safe_load(fh)
    return data if isinstance(data, dict) else {}


def _registry_capability_ids() -> set[str]:
    ids: set[str] = set()
    for cap_file in CAPABILITIES_DIR.glob("*.yaml"):
        if cap_file.name.startswith("_"):
            continue
        data = _load_yaml(cap_file)
        cap_id = data.get("id")
        if isinstance(cap_id, str) and cap_id:
            ids.add(cap_id)
    return ids


def _discover_bindings() -> tuple[
    dict[str, str],
    list[tuple[Path, str]],
    dict[str, list[str]],
]:
    binding_by_id: dict[str, str] = {}
    binding_cap_refs: list[tuple[Path, str]] = []
    bindings_by_capability: dict[str, list[str]] = {}

    for path in sorted(BINDINGS_DIR.rglob("*.yaml")):
        data = _load_yaml(path)
        binding_id = data.get("id")
        capability = data.get("capability")

        if isinstance(binding_id, str) and binding_id:
            binding_by_id[binding_id] = str(path.relative_to(ROOT)).replace("\\", "/")

        if isinstance(capability, str) and capability:
            binding_cap_refs.append((path, capability))
            if isinstance(binding_id, str) and binding_id:
                bindings_by_capability.setdefault(capability, []).append(binding_id)

    return binding_by_id, binding_cap_refs, bindings_by_capability


def _read_smoke_capabilities() -> list[str]:
    with SMOKE_LIST_PATH.open("r", encoding="utf-8") as fh:
        raw = json.load(fh)
    if not isinstance(raw, list) or not all(isinstance(i, str) for i in raw):
        raise ValueError("smoke_capabilities.json must be a JSON array of strings")
    return raw


def _read_default_selection() -> dict[str, str]:
    data = _load_yaml(DEFAULT_SELECTION_PATH)
    defaults = data.get("defaults")
    if not isinstance(defaults, dict):
        return {}
    return {
        str(cap_id): str(binding_id)
        for cap_id, binding_id in defaults.items()
        if isinstance(cap_id, str) and isinstance(binding_id, str)
    }


def _read_active_bindings() -> dict[str, str]:
    if not ACTIVE_BINDINGS_PATH.exists():
        return {}

    with ACTIVE_BINDINGS_PATH.open("r", encoding="utf-8") as fh:
        raw = json.load(fh)

    if not isinstance(raw, dict):
        raise ValueError("active_bindings.json must be an object mapping strings")

    return {
        str(cap_id): str(binding_id)
        for cap_id, binding_id in raw.items()
        if isinstance(cap_id, str) and isinstance(binding_id, str)
    }


def _load_deprecated_binding_ids() -> set[str]:
    artifacts_dir = ROOT / "artifacts"
    manifests = sorted(artifacts_dir.glob(DEPRECATED_MANIFEST_GLOB))
    if not manifests:
        return set()

    manifest = manifests[-1]
    deprecated_ids: set[str] = set()

    with manifest.open("r", encoding="utf-8") as fh:
        for i, line in enumerate(fh):
            line = line.strip()
            if not line:
                continue
            if i == 0 and line.startswith("capability\tfile"):
                continue
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            rel = parts[1].strip()
            if not rel:
                continue
            path = ROOT / rel
            if not path.exists():
                continue
            data = _load_yaml(path)
            binding_id = data.get("id")
            if isinstance(binding_id, str) and binding_id:
                deprecated_ids.add(binding_id)

    return deprecated_ids


def _read_governance_tools_supported_keys() -> set[str]:
    source = GOVERNANCE_TOOLS_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name) or target.id != "_SUPPORTED_TOOLS":
            continue
        if not isinstance(node.value, ast.Dict):
            continue

        out: set[str] = set()
        for key in node.value.keys:
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                out.add(key.value)
        return out

    return set()


def main() -> int:
    registry_ids = _registry_capability_ids()
    binding_by_id, binding_cap_refs, bindings_by_capability = _discover_bindings()
    smoke_caps = _read_smoke_capabilities()
    default_selection = _read_default_selection()
    active_bindings = _read_active_bindings()
    manifest_deprecated_binding_ids = _load_deprecated_binding_ids()
    governance_tool_caps = _read_governance_tools_supported_keys()

    errors: list[str] = []

    binding_capability_by_id: dict[str, str] = {}
    for path, cap_id in binding_cap_refs:
        data = _load_yaml(path)
        binding_id = data.get("id")
        if isinstance(binding_id, str) and binding_id:
            binding_capability_by_id[binding_id] = cap_id

    deprecated_binding_ids: set[str] = {
        bid
        for bid in manifest_deprecated_binding_ids
        if binding_capability_by_id.get(bid) not in registry_ids
    }
    stale_manifest_binding_ids = sorted(
        bid
        for bid in manifest_deprecated_binding_ids
        if binding_capability_by_id.get(bid) in registry_ids
    )

    for path, cap_id in binding_cap_refs:
        data = _load_yaml(path)
        binding_id = data.get("id")
        binding_id_str = binding_id if isinstance(binding_id, str) else ""
        if cap_id not in registry_ids:
            if binding_id_str and binding_id_str in deprecated_binding_ids:
                continue
            rel = str(path.relative_to(ROOT)).replace("\\", "/")
            errors.append(
                f"binding capability not in registry and not deprecated: {rel} -> {cap_id}"
            )

    uncovered_registry_caps = sorted(
        cap_id for cap_id in registry_ids if cap_id not in bindings_by_capability
    )
    for cap_id in uncovered_registry_caps:
        errors.append(f"registry capability without binding: {cap_id}")

    non_deprecated_by_capability: dict[str, list[str]] = {}
    for cap_id, binding_ids in bindings_by_capability.items():
        eligible = [bid for bid in binding_ids if bid not in deprecated_binding_ids]
        if eligible:
            non_deprecated_by_capability[cap_id] = eligible

    for cap_id in sorted(registry_ids):
        if cap_id not in non_deprecated_by_capability:
            errors.append(f"registry capability without active binding: {cap_id}")

    for cap_id in smoke_caps:
        if cap_id not in registry_ids:
            errors.append(f"smoke capability not in registry: {cap_id}")

    for cap_id, binding_id in default_selection.items():
        if cap_id not in registry_ids:
            errors.append(
                f"default selection capability not in registry: {cap_id} -> {binding_id}"
            )
            continue

        binding_path = binding_by_id.get(binding_id)
        if binding_path is None:
            errors.append(
                f"default selection binding does not exist: {cap_id} -> {binding_id}"
            )
            continue

        binding_yaml = _load_yaml(ROOT / binding_path)
        binding_cap = binding_yaml.get("capability")
        if not isinstance(binding_cap, str):
            errors.append(
                f"default selection binding without capability: {cap_id} -> {binding_id}"
            )
            continue

        if binding_cap not in registry_ids:
            errors.append(
                f"default selection binding capability not in registry: {binding_id} -> {binding_cap}"
            )
            continue

        if binding_cap != cap_id:
            errors.append(
                "default selection mismatch: "
                f"{cap_id} -> {binding_id} declares capability {binding_cap}"
            )

        if binding_id in deprecated_binding_ids:
            errors.append(
                f"default selection uses deprecated binding: {cap_id} -> {binding_id}"
            )

    for cap_id, binding_id in active_bindings.items():
        if cap_id not in registry_ids:
            errors.append(
                f"active binding capability not in registry: {cap_id} -> {binding_id}"
            )
            continue

        binding_path = binding_by_id.get(binding_id)
        if binding_path is None:
            errors.append(f"active binding does not exist: {cap_id} -> {binding_id}")
            continue

        binding_yaml = _load_yaml(ROOT / binding_path)
        binding_cap = binding_yaml.get("capability")
        if not isinstance(binding_cap, str):
            errors.append(
                f"active binding without capability: {cap_id} -> {binding_id}"
            )
            continue

        if binding_cap != cap_id:
            errors.append(
                "active binding mismatch: "
                f"{cap_id} -> {binding_id} declares capability {binding_cap}"
            )

        if binding_id in deprecated_binding_ids:
            errors.append(f"active binding uses deprecated binding: {cap_id} -> {binding_id}")

    for cap_id in sorted(governance_tool_caps):
        if cap_id not in registry_ids:
            errors.append(f"governance tool capability not in registry: {cap_id}")

    print("Registry capability reference verification")
    print(f"- registry capabilities: {len(registry_ids)}")
    print(f"- bindings scanned: {len(binding_cap_refs)}")
    print(f"- capabilities with >=1 binding: {len(bindings_by_capability)}")
    print(
        "- capabilities with >=1 non-deprecated binding: "
        f"{len(non_deprecated_by_capability)}"
    )
    print(f"- smoke capabilities: {len(smoke_caps)}")
    print(f"- default selections: {len(default_selection)}")
    print(f"- active selections: {len(active_bindings)}")
    print(f"- governance tool capabilities: {len(governance_tool_caps)}")
    print(
        "- deprecated bindings manifest entries: "
        f"{len(manifest_deprecated_binding_ids)}"
    )
    print(f"- deprecated bindings effective: {len(deprecated_binding_ids)}")
    print(f"- deprecated manifest stale entries: {len(stale_manifest_binding_ids)}")

    if errors:
        print("\nFound reference issues:")
        for item in errors:
            print(f"- {item}")
        return 1

    print("\nAll references are aligned with registry capabilities.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

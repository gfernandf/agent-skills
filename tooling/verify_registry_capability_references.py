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


def _discover_bindings() -> tuple[dict[str, str], list[tuple[Path, str]]]:
    binding_by_id: dict[str, str] = {}
    binding_cap_refs: list[tuple[Path, str]] = []

    for path in sorted(BINDINGS_DIR.rglob("*.yaml")):
        data = _load_yaml(path)
        binding_id = data.get("id")
        capability = data.get("capability")

        if isinstance(binding_id, str) and binding_id:
            binding_by_id[binding_id] = str(path.relative_to(ROOT)).replace("\\", "/")

        if isinstance(capability, str) and capability:
            binding_cap_refs.append((path, capability))

    return binding_by_id, binding_cap_refs


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


def _legacy_capability_alias_candidates(capability_id: str) -> list[str]:
    candidates: list[str] = []

    prefix_aliases = {
        "text.": "reasoning.",
        "eval.": "evaluation.",
        "model.": "reasoning.",
        "analysis.": "reasoning.",
        "provenance.": "evidence.",
        "ops.trace.": "evidence.trace.",
        "ops.event.": "perception.event.",
        "agent.input.": "decision.input.",
        "task.case.": "perception.case.",
        "task.priority.": "message.priority.",
        "task.sla.": "perception.sla.",
        "agent.option.": "reasoning.option.",
    }
    for old_prefix, new_prefix in prefix_aliases.items():
        if capability_id.startswith(old_prefix):
            candidates.append(new_prefix + capability_id[len(old_prefix) :])

    explicit_aliases = {
        "agent.task.plan": "reasoning.plan.generate",
        "agent.plan.split": "reasoning.plan.decompose",
        "agent.plan.run": "agent.plan.execute",
        "agent.plan.generate": "reasoning.plan.generate",
        "agent.plan.create": "reasoning.plan.create",
        "agent.task.delegate": "decision.task.delegate",
        "eval.option.analyze": "reasoning.option.analyze",
        "model.output.score": "evaluation.output.score",
        "model.response.validate": "evaluation.response.validate",
        "model.risk.score": "evaluation.risk.score",
        "text.content.extract": "perception.content.extract",
        "text.entity.extract": "perception.entity.extract",
        "text.keyword.extract": "perception.keyword.extract",
    }
    mapped = explicit_aliases.get(capability_id)
    if mapped:
        candidates.append(mapped)

    return list(dict.fromkeys(candidates))


def _resolve_registry_capability(
    capability_id: str, registry_ids: set[str]
) -> str | None:
    if capability_id in registry_ids:
        return capability_id
    for alias in _legacy_capability_alias_candidates(capability_id):
        if alias in registry_ids:
            return alias
    return None


def main() -> int:
    registry_ids = _registry_capability_ids()
    binding_by_id, binding_cap_refs = _discover_bindings()
    smoke_caps = _read_smoke_capabilities()
    default_selection = _read_default_selection()
    governance_tool_caps = _read_governance_tools_supported_keys()

    errors: list[str] = []

    for path, cap_id in binding_cap_refs:
        if _resolve_registry_capability(cap_id, registry_ids) is None:
            rel = str(path.relative_to(ROOT)).replace("\\", "/")
            errors.append(f"binding capability not in registry: {rel} -> {cap_id}")

    for cap_id in smoke_caps:
        if _resolve_registry_capability(cap_id, registry_ids) is None:
            errors.append(f"smoke capability not in registry: {cap_id}")

    for cap_id, binding_id in default_selection.items():
        resolved_default = _resolve_registry_capability(cap_id, registry_ids)
        if resolved_default is None:
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

        resolved_binding = _resolve_registry_capability(binding_cap, registry_ids)
        if resolved_binding is None:
            errors.append(
                f"default selection binding capability not in registry: {binding_id} -> {binding_cap}"
            )
            continue

        if resolved_binding != resolved_default:
            errors.append(
                "default selection mismatch: "
                f"{cap_id} -> {binding_id} declares capability {binding_cap}"
            )

    for cap_id in sorted(governance_tool_caps):
        if _resolve_registry_capability(cap_id, registry_ids) is None:
            errors.append(f"governance tool capability not in registry: {cap_id}")

    print("Registry capability reference verification")
    print(f"- registry capabilities: {len(registry_ids)}")
    print(f"- bindings scanned: {len(binding_cap_refs)}")
    print(f"- smoke capabilities: {len(smoke_caps)}")
    print(f"- default selections: {len(default_selection)}")
    print(f"- governance tool capabilities: {len(governance_tool_caps)}")

    if errors:
        print("\nFound reference issues:")
        for item in errors:
            print(f"- {item}")
        return 1

    print("\nAll references are aligned with registry capabilities.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

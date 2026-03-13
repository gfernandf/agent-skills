#!/usr/bin/env python3

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime.binding_registry import BindingRegistry

_ALLOWED = {"strict", "standard", "experimental"}


def _profile(binding) -> str:
    metadata = binding.metadata if isinstance(binding.metadata, dict) else {}
    value = metadata.get("conformance_profile")
    if isinstance(value, str) and value:
        return value
    return "standard"


def main() -> int:
    registry = BindingRegistry(repo_root=ROOT, host_root=ROOT)

    violations: list[str] = []

    # 1) Every official default must have a valid effective profile.
    for capability_id, binding_id in registry._official_defaults.items():
        binding = registry.get_binding(binding_id)
        profile = _profile(binding)
        if profile not in _ALLOWED:
            violations.append(
                f"Capability '{capability_id}' default binding '{binding_id}' has invalid profile '{profile}'."
            )

    # 2) Guardrail: official defaults should not be experimental.
    for capability_id, binding_id in registry._official_defaults.items():
        binding = registry.get_binding(binding_id)
        profile = _profile(binding)
        if profile == "experimental":
            violations.append(
                f"Capability '{capability_id}' default binding '{binding_id}' is experimental."
            )

    if violations:
        print("Binding conformance suite failed:")
        for item in violations:
            print(f"- {item}")
        return 1

    print("Binding conformance suite passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

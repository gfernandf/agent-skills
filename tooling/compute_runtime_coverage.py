from __future__ import annotations

import json
from pathlib import Path

from runtime.binding_registry import BindingRegistry
from runtime.capability_loader import YamlCapabilityLoader


def compute_runtime_coverage(repo_root: Path, host_root: Path | None = None) -> dict:
    """
    Compute how many capabilities are executable given the current binding registry.

    A capability is considered executable if:
    - at least one binding exists for it
    """

    capability_loader = YamlCapabilityLoader(repo_root)
    binding_registry = BindingRegistry(repo_root, host_root)

    capabilities_root = repo_root / "capabilities"

    capability_ids: list[str] = []

    for path in capabilities_root.glob("*.yaml"):
        raw = path.read_text(encoding="utf-8")
        if "id:" in raw:
            # quick read to avoid full parsing for coverage
            for line in raw.splitlines():
                if line.startswith("id:"):
                    capability_ids.append(line.split(":", 1)[1].strip())
                    break

    covered = 0
    uncovered: list[str] = []

    for capability_id in capability_ids:
        bindings = binding_registry.get_bindings_for_capability(capability_id)

        if bindings:
            covered += 1
        else:
            uncovered.append(capability_id)

    total = len(capability_ids)

    return {
        "total_capabilities": total,
        "covered_capabilities": covered,
        "uncovered_capabilities": uncovered,
        "coverage_ratio": covered / total if total else 0.0,
    }


def main() -> None:
    repo_root = Path.cwd()
    host_root = Path.cwd()

    stats = compute_runtime_coverage(repo_root, host_root)

    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
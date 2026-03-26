from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from runtime.binding_registry import BindingRegistry
from runtime.capability_loader import YamlCapabilityLoader


def compute_runtime_coverage(
    registry_root: Path, runtime_root: Path, host_root: Path | None = None
) -> dict:
    """
    Compute how many capabilities are executable given the current binding registry.

    A capability is considered executable if:
    - at least one binding exists for it
    """

    YamlCapabilityLoader(registry_root)
    binding_registry = BindingRegistry(runtime_root, host_root)

    capabilities_root = registry_root / "capabilities"

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
    parser = argparse.ArgumentParser(prog="compute_runtime_coverage")
    parser.add_argument(
        "--registry-root", type=Path, default=None, help="Path to the registry root"
    )
    parser.add_argument(
        "--runtime-root", type=Path, default=None, help="Path to the runtime root"
    )
    parser.add_argument(
        "--host-root", type=Path, default=None, help="Path to the host root"
    )
    args = parser.parse_args()

    registry_root = args.registry_root or Path.cwd().parent / "agent-skill-registry"
    runtime_root = args.runtime_root or Path.cwd()
    host_root = args.host_root or runtime_root

    stats = compute_runtime_coverage(registry_root, runtime_root, host_root)

    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()

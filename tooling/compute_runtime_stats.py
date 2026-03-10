from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from runtime.binding_registry import BindingRegistry
from runtime.capability_loader import YamlCapabilityLoader
from runtime.skill_loader import YamlSkillLoader


def compute_runtime_stats(registry_root: Path, runtime_root: Path, host_root: Path | None = None) -> dict:
    """
    Compute global runtime ecosystem statistics.

    This aggregates:
    - capabilities
    - bindings
    - services
    - skills
    """

    capability_loader = YamlCapabilityLoader(registry_root)
    skill_loader = YamlSkillLoader(registry_root)
    binding_registry = BindingRegistry(runtime_root, host_root)

    capabilities_root = registry_root / "capabilities"
    skills_root = registry_root / "skills"

    capability_count = 0
    for file in capabilities_root.glob("*.yaml"):
        if file.name == "_index.yaml":
            continue
        raw = file.read_text(encoding="utf-8")
        if "id:" in raw:
            capability_count += 1

    skill_count = 0
    for _ in skills_root.glob("*/*/*/skill.yaml"):
        skill_count += 1

    services = binding_registry.list_services()
    bindings = binding_registry.list_bindings()

    service_count = len(services)
    binding_count = len(bindings)

    services_by_kind: dict[str, int] = {}
    for service in services:
        services_by_kind[service.kind] = services_by_kind.get(service.kind, 0) + 1

    bindings_by_source: dict[str, int] = {}
    for binding in bindings:
        bindings_by_source[binding.source] = bindings_by_source.get(binding.source, 0) + 1

    return {
        "capabilities": capability_count,
        "skills": skill_count,
        "services": service_count,
        "bindings": binding_count,
        "services_by_kind": services_by_kind,
        "bindings_by_source": bindings_by_source,
    }


def main() -> None:
    parser = argparse.ArgumentParser(prog="compute_runtime_stats")
    parser.add_argument("--registry-root", type=Path, default=None, help="Path to the registry root")
    parser.add_argument("--runtime-root", type=Path, default=None, help="Path to the runtime root")
    parser.add_argument("--host-root", type=Path, default=None, help="Path to the host root")
    args = parser.parse_args()
    
    registry_root = args.registry_root or Path.cwd().parent / "agent-skill-registry"
    runtime_root = args.runtime_root or Path.cwd()
    host_root = args.host_root or runtime_root

    stats = compute_runtime_stats(registry_root, runtime_root, host_root)

    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
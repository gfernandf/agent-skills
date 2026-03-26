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


def compute_skill_executability(
    registry_root: Path, runtime_root: Path, host_root: Path | None = None
) -> dict:
    """
    Determine which skills are executable given the current binding registry.

    A skill is considered executable if:
    - every capability referenced by its steps has at least one binding
    """

    skill_loader = YamlSkillLoader(registry_root)
    capability_loader = YamlCapabilityLoader(registry_root)
    binding_registry = BindingRegistry(runtime_root, host_root)

    skills_root = registry_root / "skills"

    executable = []
    non_executable = []

    for skill_file in skills_root.glob("*/*/*/skill.yaml"):
        skill = skill_loader._normalize_skill(
            raw=_load_yaml(skill_file),
            path=skill_file,
        )

        missing_capabilities = []

        for step in skill.steps:
            if step.uses.startswith("skill:"):
                # nested skill dependency is considered resolvable at runtime
                continue

            capability_id = step.uses

            try:
                capability_loader.get_capability(capability_id)
            except Exception:
                missing_capabilities.append(capability_id)
                continue

            bindings = binding_registry.get_bindings_for_capability(capability_id)

            if not bindings:
                missing_capabilities.append(capability_id)

        if missing_capabilities:
            non_executable.append(
                {
                    "skill": skill.id,
                    "missing_capabilities": sorted(set(missing_capabilities)),
                }
            )
        else:
            executable.append(skill.id)

    total = len(executable) + len(non_executable)

    return {
        "total_skills": total,
        "executable_skills": len(executable),
        "non_executable_skills": non_executable,
        "executability_ratio": len(executable) / total if total else 0.0,
    }


def _load_yaml(path: Path):
    import yaml

    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main() -> None:
    parser = argparse.ArgumentParser(prog="compute_skill_executability")
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

    stats = compute_skill_executability(registry_root, runtime_root, host_root)

    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()

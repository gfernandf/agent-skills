from __future__ import annotations

import json
from pathlib import Path

from runtime.binding_registry import BindingRegistry
from runtime.capability_loader import YamlCapabilityLoader
from runtime.skill_loader import YamlSkillLoader


def compute_skill_executability(repo_root: Path, host_root: Path | None = None) -> dict:
    """
    Determine which skills are executable given the current binding registry.

    A skill is considered executable if:
    - every capability referenced by its steps has at least one binding
    """

    skill_loader = YamlSkillLoader(repo_root)
    capability_loader = YamlCapabilityLoader(repo_root)
    binding_registry = BindingRegistry(repo_root, host_root)

    skills_root = repo_root / "skills"

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
            non_executable.append({
                "skill": skill.id,
                "missing_capabilities": sorted(set(missing_capabilities)),
            })
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
    repo_root = Path.cwd()
    host_root = Path.cwd()

    stats = compute_skill_executability(repo_root, host_root)

    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
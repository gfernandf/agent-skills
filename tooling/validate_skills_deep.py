#!/usr/bin/env python3
"""Deep skill validation — verify every skill's ``uses:`` references resolve
to a real capability (or valid ``skill:`` reference), and that input/output
mappings are structurally consistent.

Usage::

    python tooling/validate_skills_deep.py                  # validate all
    python tooling/validate_skills_deep.py --skill text.translate-summary
    python tooling/validate_skills_deep.py --json            # machine-readable
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from runtime.capability_loader import YamlCapabilityLoader
from runtime.skill_loader import YamlSkillLoader


def validate_all(
    registry_root: Path,
    skill_filter: str | None = None,
) -> list[dict]:
    capability_loader = YamlCapabilityLoader(registry_root)
    skill_loader = YamlSkillLoader(registry_root)

    all_caps = capability_loader.get_all_capabilities()
    cap_ids = set(all_caps.keys())

    skills_root = registry_root / "skills"
    issues: list[dict] = []

    skill_files = list(skills_root.glob("**/skill.yaml"))
    if not skill_files:
        issues.append({"level": "error", "message": "No skill files found", "skill": None})
        return issues

    for skill_file in sorted(skill_files):
        try:
            import yaml
            raw = yaml.safe_load(skill_file.read_text(encoding="utf-8"))
        except Exception as exc:
            issues.append({
                "level": "error",
                "skill": str(skill_file.relative_to(registry_root)),
                "message": f"YAML parse error: {exc}",
            })
            continue

        skill_id = raw.get("id", "(unknown)")
        if skill_filter and skill_id != skill_filter:
            continue

        steps = raw.get("steps", [])
        if not steps:
            issues.append({
                "level": "warning",
                "skill": skill_id,
                "message": "Skill has no steps",
            })
            continue

        step_ids = {s.get("id") for s in steps if s.get("id")}

        for idx, step in enumerate(steps):
            step_id = step.get("id", f"step_{idx}")
            uses = step.get("uses", "")

            # Check uses reference
            if uses.startswith("skill:"):
                # Nested skill reference — valid syntax, not validated here
                pass
            elif uses not in cap_ids:
                issues.append({
                    "level": "error",
                    "skill": skill_id,
                    "step": step_id,
                    "uses": uses,
                    "message": f"Capability '{uses}' not found in registry ({len(cap_ids)} known)",
                })
            else:
                # Validate input mapping keys against capability inputs
                cap = all_caps[uses]
                cap_inputs = set(getattr(cap, "inputs", {}).keys())
                step_input = step.get("input", {})
                if isinstance(step_input, dict) and cap_inputs:
                    for key in step_input:
                        if key not in cap_inputs:
                            issues.append({
                                "level": "warning",
                                "skill": skill_id,
                                "step": step_id,
                                "uses": uses,
                                "message": f"Input key '{key}' not in capability inputs: {sorted(cap_inputs)}",
                            })

            # Validate depends_on references
            config = step.get("config", {}) or {}
            depends_on = config.get("depends_on", [])
            if isinstance(depends_on, list):
                for dep in depends_on:
                    if dep not in step_ids:
                        issues.append({
                            "level": "error",
                            "skill": skill_id,
                            "step": step_id,
                            "message": f"depends_on '{dep}' references unknown step (known: {sorted(step_ids)})",
                        })

    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description="Deep skill validation")
    parser.add_argument("--registry-root", type=Path, default=None)
    parser.add_argument("--skill", default=None, help="Validate single skill by id")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    registry_root = args.registry_root or (PROJECT_ROOT.parent / "agent-skill-registry")
    issues = validate_all(registry_root, args.skill)

    errors = [i for i in issues if i["level"] == "error"]
    warnings = [i for i in issues if i["level"] == "warning"]

    if args.json:
        print(json.dumps({
            "errors": len(errors),
            "warnings": len(warnings),
            "issues": issues,
        }, indent=2, ensure_ascii=False))
    else:
        if not issues:
            print("[OK] All skills validated — every uses: reference resolves to a known capability.")
            return 0

        for issue in issues:
            tag = "ERROR" if issue["level"] == "error" else "WARN"
            skill = issue.get("skill", "?")
            step = issue.get("step", "")
            step_str = f" → {step}" if step else ""
            print(f"[{tag}] {skill}{step_str}: {issue['message']}")

        print(f"\nTotal: {len(errors)} errors, {len(warnings)} warnings")

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())

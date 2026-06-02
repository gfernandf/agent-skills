#!/usr/bin/env python3

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
PYPROJECT = ROOT / "pyproject.toml"
CITATION = ROOT / "CITATION.cff"
REGISTRY_STATS = ROOT.parent / "agent-skill-registry" / "catalog" / "stats.json"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _extract_badge_count(readme: str, label: str) -> int:
    pattern = rf"{re.escape(label)}-(\d+)-"
    m = re.search(pattern, readme)
    if not m:
        raise ValueError(f"missing README badge for {label}")
    return int(m.group(1))


def _extract_pyproject_version(text: str) -> str:
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, flags=re.MULTILINE)
    if not m:
        raise ValueError("missing version in pyproject.toml")
    return m.group(1)


def _extract_cff_version(text: str) -> str:
    m = re.search(r"^version:\s*([0-9A-Za-z_.-]+)", text, flags=re.MULTILINE)
    if not m:
        raise ValueError("missing version in CITATION.cff")
    return m.group(1)


def _extract_readme_software_citation_version(text: str) -> str:
    m = re.search(r"version\s*=\s*\{([0-9A-Za-z_.-]+)\}", text)
    if not m:
        raise ValueError("missing software citation version in README")
    return m.group(1)


def main() -> int:
    issues: list[str] = []

    try:
        readme_text = _read(README)
        pyproject_text = _read(PYPROJECT)
        citation_text = _read(CITATION)
    except Exception as exc:
        print(f"error: failed reading core project files: {exc}")
        return 1

    try:
        cap_badge = _extract_badge_count(readme_text, "Capabilities")
        skills_badge = _extract_badge_count(readme_text, "Skills")
    except Exception as exc:
        issues.append(str(exc))
        cap_badge = -1
        skills_badge = -1

    stats_cap = None
    stats_skills = None
    if not REGISTRY_STATS.exists():
        issues.append(
            f"registry stats file missing: {REGISTRY_STATS} (did you checkout agent-skill-registry?)"
        )
    else:
        try:
            stats = json.loads(REGISTRY_STATS.read_text(encoding="utf-8"))
            summary = stats.get("summary", {})
            stats_cap = int(summary.get("capability_count"))
            stats_skills = int(summary.get("skill_count"))
        except Exception as exc:
            issues.append(f"invalid registry stats json: {exc}")

    if stats_cap is not None and cap_badge != stats_cap:
        issues.append(
            f"README Capabilities badge drift: {cap_badge} != registry {stats_cap}"
        )
    if stats_skills is not None and skills_badge != stats_skills:
        issues.append(
            f"README Skills badge drift: {skills_badge} != registry {stats_skills}"
        )

    try:
        pyproject_version = _extract_pyproject_version(pyproject_text)
    except Exception as exc:
        issues.append(str(exc))
        pyproject_version = ""

    try:
        cff_version = _extract_cff_version(citation_text)
    except Exception as exc:
        issues.append(str(exc))
        cff_version = ""

    try:
        readme_software_version = _extract_readme_software_citation_version(readme_text)
    except Exception as exc:
        issues.append(str(exc))
        readme_software_version = ""

    if pyproject_version and cff_version and pyproject_version != cff_version:
        issues.append(
            "version drift: pyproject.toml "
            f"({pyproject_version}) != CITATION.cff ({cff_version})"
        )
    if (
        pyproject_version
        and readme_software_version
        and pyproject_version != readme_software_version
    ):
        issues.append(
            "version drift: pyproject.toml "
            f"({pyproject_version}) != README software citation ({readme_software_version})"
        )

    print("Doc/version drift check")
    print(f"- pyproject version: {pyproject_version or 'unknown'}")
    print(f"- citation version: {cff_version or 'unknown'}")
    print(f"- README software citation version: {readme_software_version or 'unknown'}")
    print(f"- README badges: capabilities={cap_badge}, skills={skills_badge}")
    print(
        f"- registry stats: capabilities={stats_cap if stats_cap is not None else 'unknown'}, "
        f"skills={stats_skills if stats_skills is not None else 'unknown'}"
    )

    if issues:
        print("- status: failed")
        for issue in issues:
            print(f"  * {issue}")
        return 1

    print("- status: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

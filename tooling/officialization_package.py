from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml


ALLOWED_CHANNELS = {"experimental", "community", "official"}


@dataclass
class PreparationResult:
    package_root: Path
    payload_skill_path: Path
    skill_id: str
    target_channel: str


@dataclass
class ValidationResult:
    ok: bool
    errors: list[str]
    warnings: list[str]
    skill_id: str | None
    target_channel: str | None


def _load_capability_ids(registry_root: Path) -> set[str]:
    catalog_path = registry_root / "catalog" / "capabilities.json"
    if not catalog_path.exists():
        return set()

    raw = json.loads(catalog_path.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        capabilities = raw.get("capabilities", [])
    else:
        capabilities = raw

    ids: set[str] = set()
    if isinstance(capabilities, list):
        for item in capabilities:
            if isinstance(item, dict):
                cid = item.get("id")
                if isinstance(cid, str) and cid:
                    ids.add(cid)
    return ids


def _resolve_skill_file(local_skills_root: Path, skill_id: str | None, skill_file: Path | None) -> Path:
    if skill_file is not None:
        if not skill_file.exists():
            raise FileNotFoundError(f"skill file not found: {skill_file}")
        return skill_file

    if not skill_id:
        raise ValueError("Provide either skill_id or skill_file.")

    if "." not in skill_id:
        raise ValueError(f"Invalid skill_id '{skill_id}'. Expected format domain.slug")

    domain, slug = skill_id.split(".", 1)
    direct = local_skills_root / domain / slug / "skill.yaml"
    if direct.exists():
        return direct

    # Fallback: scan local root for matching id.
    for path in local_skills_root.glob("**/skill.yaml"):
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(raw, dict) and raw.get("id") == skill_id:
            return path

    raise FileNotFoundError(
        f"Could not find local skill '{skill_id}' in {local_skills_root}. "
        "Use --skill-file to provide an explicit path."
    )


def _read_skill_doc(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Skill file {path} is not a YAML mapping")
    return raw


def prepare_officialization_package(
    *,
    local_skills_root: Path,
    registry_root: Path,
    target_channel: str,
    out_root: Path,
    skill_id: str | None = None,
    skill_file: Path | None = None,
) -> PreparationResult:
    if target_channel not in ALLOWED_CHANNELS:
        raise ValueError(
            f"target_channel must be one of {sorted(ALLOWED_CHANNELS)}."
        )

    source_skill_file = _resolve_skill_file(local_skills_root, skill_id, skill_file)
    skill_doc = _read_skill_doc(source_skill_file)

    resolved_skill_id = skill_doc.get("id")
    if not isinstance(resolved_skill_id, str) or not resolved_skill_id:
        raise ValueError("Skill must define a non-empty 'id'.")

    if "." not in resolved_skill_id:
        raise ValueError(f"Skill id '{resolved_skill_id}' must be domain.slug")

    domain, slug = resolved_skill_id.split(".", 1)

    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    package_name = f"{resolved_skill_id.replace('.', '_')}-{target_channel}-{timestamp}"
    package_root = out_root / package_name

    payload_skill_dir = package_root / "payload" / "skills" / target_channel / domain / slug
    payload_skill_dir.mkdir(parents=True, exist_ok=True)
    payload_skill_path = payload_skill_dir / "skill.yaml"
    shutil.copy2(source_skill_file, payload_skill_path)

    evidence_dir = package_root / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    admission_answers = {
        "problem_statement": "TODO",
        "differentiation": {
            "overlapping_ids": [],
            "why_not_extend_existing": "TODO",
        },
        "business_value": "TODO",
        "contract_clarity": "TODO",
        "sunset_plan": "TODO",
    }
    (evidence_dir / "admission_answers.yaml").write_text(
        yaml.dump(admission_answers, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    metadata = {
        "skill_id": resolved_skill_id,
        "source_skill_file": str(source_skill_file),
        "target_channel": target_channel,
        "prepared_at_utc": timestamp,
        "registry_root": str(registry_root),
    }
    (package_root / "package_manifest.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    pr_body = (
        "## Change Type\n\n"
        "- [x] New skill\n\n"
        "## Problem Statement\n\n"
        "TODO\n\n"
        "## Differentiation Check (Required for new skills/capabilities)\n\n"
        "- Overlapping IDs: TODO\n"
        "- Why not extend existing artifact: TODO\n\n"
        "## Canonical-First Check\n\n"
        "- [x] I reviewed docs/SKILL_ADMISSION_POLICY.md\n"
        "- [x] I verified this does not introduce avoidable semantic duplication\n"
        "- [ ] If overlap exists, I documented merge/deprecation rationale\n\n"
        "## Contract and Metadata Quality\n\n"
        "- [ ] Inputs/outputs are stable and reusable\n"
        "- [ ] Metadata includes tags\n"
        "- [ ] Skill metadata includes use_cases and examples (when applicable)\n\n"
        "## Lifecycle and Sunset\n\n"
        "- [ ] Lifecycle intent is documented (draft / validated / etc.)\n"
        "- [ ] If this supersedes an artifact, migration/sunset notes are included\n\n"
        "## Validation Evidence\n\n"
        "Paste output from: python tools/validate_registry.py and python tools/governance_guardrails.py\n\n"
        "## Notes for Maintainers\n\n"
        "TODO\n"
    )
    (package_root / "pr_body_template.md").write_text(pr_body, encoding="utf-8")

    return PreparationResult(
        package_root=package_root,
        payload_skill_path=payload_skill_path,
        skill_id=resolved_skill_id,
        target_channel=target_channel,
    )


def _is_todo(value: Any) -> bool:
    if isinstance(value, str):
        txt = value.strip().lower()
        return txt in {"todo", "tbd", "pending", ""} or txt.startswith("todo")
    return False


def validate_officialization_package(
    *,
    package_root: Path,
    registry_root: Path,
) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []

    manifest_path = package_root / "package_manifest.json"
    if not manifest_path.exists():
        return ValidationResult(
            ok=False,
            errors=[f"Missing manifest: {manifest_path}"],
            warnings=[],
            skill_id=None,
            target_channel=None,
        )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    skill_id = manifest.get("skill_id")
    target_channel = manifest.get("target_channel")

    if not isinstance(skill_id, str) or not skill_id:
        errors.append("Manifest skill_id is missing/invalid")

    if target_channel not in ALLOWED_CHANNELS:
        errors.append("Manifest target_channel is missing/invalid")

    payload_dir = package_root / "payload" / "skills"
    skill_files = list(payload_dir.glob("**/skill.yaml"))
    if len(skill_files) != 1:
        errors.append(
            f"Package must contain exactly one payload skill.yaml under {payload_dir}, found {len(skill_files)}"
        )
        return ValidationResult(
            ok=False,
            errors=errors,
            warnings=warnings,
            skill_id=skill_id if isinstance(skill_id, str) else None,
            target_channel=target_channel if isinstance(target_channel, str) else None,
        )

    skill_file = skill_files[0]
    try:
        skill_doc = _read_skill_doc(skill_file)
    except Exception as exc:
        errors.append(f"Invalid payload skill YAML: {exc}")
        return ValidationResult(
            ok=False,
            errors=errors,
            warnings=warnings,
            skill_id=skill_id if isinstance(skill_id, str) else None,
            target_channel=target_channel if isinstance(target_channel, str) else None,
        )

    # Core shape validation
    for field in ("id", "version", "name", "description"):
        value = skill_doc.get(field)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"Skill field '{field}' must be a non-empty string")

    skill_steps = skill_doc.get("steps")
    if not isinstance(skill_steps, list) or not skill_steps:
        errors.append("Skill 'steps' must be a non-empty list")
    else:
        seen_step_ids: set[str] = set()
        for idx, step in enumerate(skill_steps):
            if not isinstance(step, dict):
                errors.append(f"Step[{idx}] must be a mapping")
                continue

            sid = step.get("id")
            if not isinstance(sid, str) or not sid:
                errors.append(f"Step[{idx}] missing non-empty 'id'")
            elif sid in seen_step_ids:
                errors.append(f"Duplicate step id: {sid}")
            else:
                seen_step_ids.add(sid)

            uses = step.get("uses")
            if not isinstance(uses, str) or not uses:
                errors.append(f"Step[{idx}] missing non-empty 'uses'")

    # id/path consistency
    if isinstance(skill_id, str) and isinstance(skill_doc.get("id"), str):
        if skill_doc["id"] != skill_id:
            errors.append(
                f"Payload skill id '{skill_doc['id']}' does not match manifest skill_id '{skill_id}'"
            )

    # Ensure payload path matches channel/domain/slug
    if isinstance(skill_doc.get("id"), str) and "." in skill_doc["id"] and isinstance(target_channel, str):
        domain, slug = skill_doc["id"].split(".", 1)
        expected = package_root / "payload" / "skills" / target_channel / domain / slug / "skill.yaml"
        if skill_file.resolve() != expected.resolve():
            errors.append(
                f"Payload path mismatch. Expected {expected}, found {skill_file}"
            )

    # Capability reference check
    capability_ids = _load_capability_ids(registry_root)
    for step in skill_doc.get("steps", []) if isinstance(skill_doc.get("steps"), list) else []:
        if not isinstance(step, dict):
            continue
        uses = step.get("uses")
        if isinstance(uses, str) and uses and not uses.startswith("skill:"):
            if capability_ids and uses not in capability_ids:
                errors.append(f"Unknown capability reference in step '{step.get('id', '?')}': {uses}")

    # Metadata quality checks for community/official
    metadata = skill_doc.get("metadata")
    if target_channel in {"community", "official"}:
        if not isinstance(metadata, dict):
            errors.append("metadata block is required for community/official promotion")
        else:
            for key in ("tags", "use_cases", "examples"):
                value = metadata.get(key)
                if not isinstance(value, list) or not value:
                    errors.append(
                        f"metadata.{key} must be a non-empty list for {target_channel} channel"
                    )

    # Admission answers checks
    answers_path = package_root / "evidence" / "admission_answers.yaml"
    if not answers_path.exists():
        errors.append(f"Missing admission answers file: {answers_path}")
    else:
        try:
            answers = yaml.safe_load(answers_path.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"Invalid admission answers YAML: {exc}")
            answers = None

        if isinstance(answers, dict):
            required = [
                "problem_statement",
                "business_value",
                "contract_clarity",
            ]
            if target_channel in {"community", "official"}:
                required.extend(["sunset_plan", "differentiation"])

            for key in required:
                if key not in answers:
                    errors.append(f"admission_answers missing required key '{key}'")

            problem_statement = answers.get("problem_statement")
            if _is_todo(problem_statement):
                errors.append("admission_answers.problem_statement is still TODO")

            business_value = answers.get("business_value")
            if _is_todo(business_value):
                errors.append("admission_answers.business_value is still TODO")

            contract_clarity = answers.get("contract_clarity")
            if _is_todo(contract_clarity):
                errors.append("admission_answers.contract_clarity is still TODO")

            if target_channel in {"community", "official"}:
                diff = answers.get("differentiation")
                if not isinstance(diff, dict):
                    errors.append("admission_answers.differentiation must be a mapping")
                else:
                    if _is_todo(diff.get("why_not_extend_existing")):
                        errors.append(
                            "admission_answers.differentiation.why_not_extend_existing is still TODO"
                        )

                if _is_todo(answers.get("sunset_plan")):
                    warnings.append("admission_answers.sunset_plan is TODO (required if superseding existing skill)")

    return ValidationResult(
        ok=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        skill_id=skill_id if isinstance(skill_id, str) else None,
        target_channel=target_channel if isinstance(target_channel, str) else None,
    )

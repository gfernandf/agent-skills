from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

import yaml

from runtime.errors import InvalidSkillSpecError, SkillNotFoundError
from runtime.models import FieldSpec, SkillSpec, StepSpec


class SkillLoader(Protocol):
    def get_skill(self, skill_id: str) -> SkillSpec:
        """
        Return the normalized SkillSpec for the requested skill id.

        Must raise SkillNotFoundError if the skill does not exist.
        Must raise InvalidSkillSpecError if the source exists but is invalid.
        """
        ...


class YamlSkillLoader:
    """
    YAML-backed skill loader using the registry source tree as the source of truth.

    Expected repository layout:

        skills/<channel>/<domain>/<slug>/skill.yaml
    """

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root
        self.skills_root = self.repo_root / "skills"
        self._skill_index: dict[str, Path] | None = None

    def get_skill(self, skill_id: str) -> SkillSpec:
        path = self._get_skill_path(skill_id)

        try:
            with path.open("r", encoding="utf-8-sig") as f:
                raw = yaml.safe_load(f)
        except FileNotFoundError as e:
            raise SkillNotFoundError(
                f"Skill '{skill_id}' not found.",
                skill_id=skill_id,
                cause=e,
            ) from e
        except yaml.YAMLError as e:
            raise InvalidSkillSpecError(
                f"Skill '{skill_id}' contains invalid YAML.",
                skill_id=skill_id,
                cause=e,
            ) from e
        except OSError as e:
            raise InvalidSkillSpecError(
                f"Skill '{skill_id}' could not be read.",
                skill_id=skill_id,
                cause=e,
            ) from e

        try:
            return self._normalize_skill(raw, path)
        except InvalidSkillSpecError:
            raise
        except Exception as e:
            raise InvalidSkillSpecError(
                f"Skill '{skill_id}' could not be normalized.",
                skill_id=skill_id,
                cause=e,
            ) from e

    def _get_skill_path(self, skill_id: str) -> Path:
        if self._skill_index is None:
            self._skill_index = self._build_skill_index()

        path = self._skill_index.get(skill_id)
        if path is None:
            raise SkillNotFoundError(
                f"Skill '{skill_id}' not found.",
                skill_id=skill_id,
            )
        return path

    def _build_skill_index(self) -> dict[str, Path]:
        index: dict[str, Path] = {}

        if not self.skills_root.exists():
            return index

        for path in sorted(self.skills_root.glob("*/*/*/skill.yaml")):
            if not path.is_file():
                continue

            try:
                with path.open("r", encoding="utf-8-sig") as f:
                    raw = yaml.safe_load(f)
            except Exception:
                # Invalid files are ignored at indexing time and will fail
                # explicitly if requested by id through get_skill().
                continue

            if not isinstance(raw, dict):
                continue

            raw_id = raw.get("id")
            if isinstance(raw_id, str) and raw_id:
                index[raw_id] = path

        return index

    def _normalize_skill(self, raw: Any, path: Path) -> SkillSpec:
        relpath = self._safe_relpath(path)

        if not isinstance(raw, dict):
            raise InvalidSkillSpecError(
                f"Skill document '{relpath}' must be a mapping."
            )

        skill_id = self._require_non_empty_string(raw, "id", relpath)
        version = self._require_non_empty_string(raw, "version", relpath)
        name = self._require_non_empty_string(raw, "name", relpath)
        description = self._require_non_empty_string(raw, "description", relpath)

        inputs = self._normalize_fields(raw.get("inputs"), "inputs", relpath)
        outputs = self._normalize_fields(raw.get("outputs"), "outputs", relpath)
        steps = self._normalize_steps(raw.get("steps"), relpath)
        metadata = self._normalize_metadata(raw.get("metadata"))

        channel, domain, slug = self._extract_path_metadata(path)

        return SkillSpec(
            id=skill_id,
            version=version,
            name=name,
            description=description,
            inputs=inputs,
            outputs=outputs,
            steps=steps,
            metadata=metadata,
            channel=channel,
            domain=domain,
            slug=slug,
            source_file=relpath,
        )

    def _normalize_fields(
        self,
        raw_fields: Any,
        section_name: str,
        relpath: str,
    ) -> dict[str, FieldSpec]:
        if raw_fields is None:
            raise InvalidSkillSpecError(
                f"Skill '{relpath}' is missing required section '{section_name}'."
            )

        if not isinstance(raw_fields, dict):
            raise InvalidSkillSpecError(
                f"Skill '{relpath}' section '{section_name}' must be a mapping."
            )

        normalized: dict[str, FieldSpec] = {}
        for field_name, field_value in raw_fields.items():
            if not isinstance(field_name, str) or not field_name:
                raise InvalidSkillSpecError(
                    f"Skill '{relpath}' section '{section_name}' contains an invalid field name."
                )

            if not isinstance(field_value, dict):
                raise InvalidSkillSpecError(
                    f"Skill '{relpath}' field '{section_name}.{field_name}' must be a mapping."
                )

            field_type = field_value.get("type")
            if not isinstance(field_type, str) or not field_type:
                raise InvalidSkillSpecError(
                    f"Skill '{relpath}' field '{section_name}.{field_name}' must define a non-empty string 'type'."
                )

            required = field_value.get("required", False)
            if not isinstance(required, bool):
                raise InvalidSkillSpecError(
                    f"Skill '{relpath}' field '{section_name}.{field_name}.required' must be boolean."
                )

            description = field_value.get("description")
            if description is not None and not isinstance(description, str):
                raise InvalidSkillSpecError(
                    f"Skill '{relpath}' field '{section_name}.{field_name}.description' must be a string if present."
                )

            default = field_value.get("default")

            normalized[field_name] = FieldSpec(
                type=field_type,
                required=required,
                description=description,
                default=default,
            )

        return normalized

    def _normalize_steps(self, raw_steps: Any, relpath: str) -> tuple[StepSpec, ...]:
        if raw_steps is None:
            raise InvalidSkillSpecError(
                f"Skill '{relpath}' is missing required section 'steps'."
            )

        if not isinstance(raw_steps, list):
            raise InvalidSkillSpecError(
                f"Skill '{relpath}' section 'steps' must be a list."
            )

        normalized_steps: list[StepSpec] = []
        seen_step_ids: set[str] = set()

        for idx, raw_step in enumerate(raw_steps):
            if not isinstance(raw_step, dict):
                raise InvalidSkillSpecError(
                    f"Skill '{relpath}' step at index {idx} must be a mapping."
                )

            step_id = raw_step.get("id")
            if not isinstance(step_id, str) or not step_id:
                raise InvalidSkillSpecError(
                    f"Skill '{relpath}' step at index {idx} must define a non-empty string 'id'."
                )

            if step_id in seen_step_ids:
                raise InvalidSkillSpecError(
                    f"Skill '{relpath}' contains duplicate step id '{step_id}'."
                )
            seen_step_ids.add(step_id)

            uses = raw_step.get("uses")
            if not isinstance(uses, str) or not uses:
                raise InvalidSkillSpecError(
                    f"Skill '{relpath}' step '{step_id}' must define a non-empty string 'uses'."
                )

            input_mapping = raw_step.get("input", {})
            if input_mapping is None:
                input_mapping = {}
            if not isinstance(input_mapping, dict):
                raise InvalidSkillSpecError(
                    f"Skill '{relpath}' step '{step_id}'.input must be a mapping."
                )

            output_mapping = raw_step.get("output", {})
            if output_mapping is None:
                output_mapping = {}
            if not isinstance(output_mapping, dict):
                raise InvalidSkillSpecError(
                    f"Skill '{relpath}' step '{step_id}'.output must be a mapping."
                )

            normalized_output_mapping: dict[str, str] = {}
            for output_name, target in output_mapping.items():
                if not isinstance(output_name, str) or not output_name:
                    raise InvalidSkillSpecError(
                        f"Skill '{relpath}' step '{step_id}'.output contains an invalid output field name."
                    )
                if not isinstance(target, str) or not target:
                    raise InvalidSkillSpecError(
                        f"Skill '{relpath}' step '{step_id}'.output['{output_name}'] must be a non-empty string target."
                    )
                normalized_output_mapping[output_name] = target

            config = raw_step.get("config", {})
            if config is None:
                config = {}
            if not isinstance(config, dict):
                raise InvalidSkillSpecError(
                    f"Skill '{relpath}' step '{step_id}'.config must be a mapping if present."
                )

            normalized_steps.append(
                StepSpec(
                    id=step_id,
                    uses=uses,
                    input_mapping=dict(input_mapping),
                    output_mapping=normalized_output_mapping,
                    config=dict(config),
                )
            )

        return tuple(normalized_steps)

    def _normalize_metadata(self, raw_metadata: Any) -> dict[str, Any]:
        if raw_metadata is None:
            return {}
        if not isinstance(raw_metadata, dict):
            return {}
        return dict(raw_metadata)

    def _extract_path_metadata(self, path: Path) -> tuple[str | None, str | None, str | None]:
        try:
            rel = path.relative_to(self.repo_root)
        except ValueError:
            return None, None, None

        parts = rel.parts
        # skills/<channel>/<domain>/<slug>/skill.yaml
        if len(parts) == 5 and parts[0] == "skills" and parts[4] == "skill.yaml":
            return parts[1], parts[2], parts[3]

        return None, None, None

    def _require_non_empty_string(self, raw: dict[str, Any], key: str, relpath: str) -> str:
        value = raw.get(key)
        if not isinstance(value, str) or not value:
            raise InvalidSkillSpecError(
                f"Skill '{relpath}' field '{key}' must be a non-empty string."
            )
        return value

    def _safe_relpath(self, path: Path) -> str:
        try:
            return path.relative_to(self.repo_root).as_posix()
        except ValueError:
            return path.as_posix()
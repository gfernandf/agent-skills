from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

import yaml

from runtime.errors import CapabilityNotFoundError, InvalidCapabilitySpecError
from runtime.models import CapabilitySpec, FieldSpec


class CapabilityLoader(Protocol):
    def get_capability(self, capability_id: str) -> CapabilitySpec:
        """
        Return the normalized CapabilitySpec for the requested capability id.

        Must raise CapabilityNotFoundError if the capability does not exist.
        Must raise InvalidCapabilitySpecError if the source exists but is invalid.
        """
        ...


class YamlCapabilityLoader:
    """
    YAML-backed capability loader using the registry source tree as the source of truth.

    Expected repository layout:

        capabilities/<capability-id>.yaml
    """

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root
        self.capabilities_root = self.repo_root / "capabilities"
        self._capability_index: dict[str, Path] | None = None

    def get_capability(self, capability_id: str) -> CapabilitySpec:
        path = self._get_capability_path(capability_id)

        try:
            with path.open("r", encoding="utf-8") as f:
                raw = yaml.safe_load(f)
        except FileNotFoundError as e:
            raise CapabilityNotFoundError(
                f"Capability '{capability_id}' not found.",
                capability_id=capability_id,
                cause=e,
            ) from e
        except yaml.YAMLError as e:
            raise InvalidCapabilitySpecError(
                f"Capability '{capability_id}' contains invalid YAML.",
                capability_id=capability_id,
                cause=e,
            ) from e
        except OSError as e:
            raise InvalidCapabilitySpecError(
                f"Capability '{capability_id}' could not be read.",
                capability_id=capability_id,
                cause=e,
            ) from e

        try:
            return self._normalize_capability(raw, path)
        except InvalidCapabilitySpecError:
            raise
        except Exception as e:
            raise InvalidCapabilitySpecError(
                f"Capability '{capability_id}' could not be normalized.",
                capability_id=capability_id,
                cause=e,
            ) from e

    def _get_capability_path(self, capability_id: str) -> Path:
        if self._capability_index is None:
            self._capability_index = self._build_capability_index()

        path = self._capability_index.get(capability_id)
        if path is None:
            raise CapabilityNotFoundError(
                f"Capability '{capability_id}' not found.",
                capability_id=capability_id,
            )
        return path

    def _build_capability_index(self) -> dict[str, Path]:
        index: dict[str, Path] = {}

        if not self.capabilities_root.exists():
            return index

        for path in sorted(self.capabilities_root.glob("*.yaml")):
            if not path.is_file() or path.name == "_index.yaml":
                continue

            try:
                with path.open("r", encoding="utf-8") as f:
                    raw = yaml.safe_load(f)
            except Exception:
                # Invalid files are ignored at indexing time and will fail
                # explicitly if requested by id through get_capability().
                continue

            if not isinstance(raw, dict):
                continue

            raw_id = raw.get("id")
            if isinstance(raw_id, str) and raw_id:
                index[raw_id] = path

        return index

    def _normalize_capability(self, raw: Any, path: Path) -> CapabilitySpec:
        if not isinstance(raw, dict):
            raise InvalidCapabilitySpecError(
                f"Capability document '{self._safe_relpath(path)}' must be a mapping."
            )

        capability_id = self._require_non_empty_string(raw, "id", path)
        version = self._require_non_empty_string(raw, "version", path)
        description = self._require_non_empty_string(raw, "description", path)

        inputs = self._normalize_fields(raw.get("inputs"), "inputs", path)
        outputs = self._normalize_fields(raw.get("outputs"), "outputs", path)

        metadata = self._normalize_metadata(raw.get("metadata"))
        properties = self._normalize_properties(raw.get("properties"), path)
        requires = self._normalize_requires(raw.get("requires"), path)
        deprecated = self._normalize_deprecated(raw.get("deprecated"), metadata, path)
        replacement = self._normalize_optional_string(raw.get("replacement"), "replacement", path)
        aliases = self._normalize_aliases(raw.get("aliases"), path)

        return CapabilitySpec(
            id=capability_id,
            version=version,
            description=description,
            inputs=inputs,
            outputs=outputs,
            metadata=metadata,
            properties=properties,
            requires=requires,
            deprecated=deprecated,
            replacement=replacement,
            aliases=aliases,
            source_file=self._safe_relpath(path),
        )

    def _normalize_fields(
        self,
        raw_fields: Any,
        section_name: str,
        path: Path,
    ) -> dict[str, FieldSpec]:
        if raw_fields is None:
            raise InvalidCapabilitySpecError(
                f"Capability '{self._safe_relpath(path)}' is missing required section '{section_name}'."
            )

        if not isinstance(raw_fields, dict):
            raise InvalidCapabilitySpecError(
                f"Capability '{self._safe_relpath(path)}' section '{section_name}' must be a mapping."
            )

        normalized: dict[str, FieldSpec] = {}
        for field_name, field_value in raw_fields.items():
            if not isinstance(field_name, str) or not field_name:
                raise InvalidCapabilitySpecError(
                    f"Capability '{self._safe_relpath(path)}' section '{section_name}' contains an invalid field name."
                )

            if not isinstance(field_value, dict):
                raise InvalidCapabilitySpecError(
                    f"Capability '{self._safe_relpath(path)}' field '{section_name}.{field_name}' must be a mapping."
                )

            field_type = field_value.get("type")
            if not isinstance(field_type, str) or not field_type:
                raise InvalidCapabilitySpecError(
                    f"Capability '{self._safe_relpath(path)}' field '{section_name}.{field_name}' must define a non-empty string 'type'."
                )

            required = field_value.get("required", False)
            if not isinstance(required, bool):
                raise InvalidCapabilitySpecError(
                    f"Capability '{self._safe_relpath(path)}' field '{section_name}.{field_name}.required' must be boolean."
                )

            description = field_value.get("description")
            if description is not None and not isinstance(description, str):
                raise InvalidCapabilitySpecError(
                    f"Capability '{self._safe_relpath(path)}' field '{section_name}.{field_name}.description' must be a string if present."
                )

            default = field_value.get("default")

            normalized[field_name] = FieldSpec(
                type=field_type,
                required=required,
                description=description,
                default=default,
            )

        return normalized

    def _normalize_metadata(self, raw_metadata: Any) -> dict[str, Any]:
        if raw_metadata is None:
            return {}
        if not isinstance(raw_metadata, dict):
            return {}
        return dict(raw_metadata)

    def _normalize_properties(self, raw_properties: Any, path: Path) -> dict[str, Any]:
        if raw_properties is None:
            return {}
        if not isinstance(raw_properties, dict):
            raise InvalidCapabilitySpecError(
                f"Capability '{self._safe_relpath(path)}' field 'properties' must be a mapping if present."
            )
        return dict(raw_properties)

    def _normalize_requires(self, raw_requires: Any, path: Path) -> tuple[str, ...]:
        if raw_requires is None:
            return ()

        if not isinstance(raw_requires, list):
            raise InvalidCapabilitySpecError(
                f"Capability '{self._safe_relpath(path)}' field 'requires' must be a list if present."
            )

        normalized: list[str] = []
        for idx, item in enumerate(raw_requires):
            if not isinstance(item, str) or not item:
                raise InvalidCapabilitySpecError(
                    f"Capability '{self._safe_relpath(path)}' field 'requires[{idx}]' must be a non-empty string."
                )
            normalized.append(item)

        return tuple(normalized)

    def _normalize_deprecated(
        self,
        raw_deprecated: Any,
        metadata: dict[str, Any],
        path: Path,
    ) -> bool | None:
        if raw_deprecated is not None:
            if not isinstance(raw_deprecated, bool):
                raise InvalidCapabilitySpecError(
                    f"Capability '{self._safe_relpath(path)}' field 'deprecated' must be boolean if present."
                )
            return raw_deprecated

        status = metadata.get("status")
        if status == "deprecated":
            return True

        return None

    def _normalize_optional_string(
        self,
        value: Any,
        field_name: str,
        path: Path,
    ) -> str | None:
        if value is None:
            return None

        if not isinstance(value, str) or not value:
            raise InvalidCapabilitySpecError(
                f"Capability '{self._safe_relpath(path)}' field '{field_name}' must be a non-empty string if present."
            )

        return value

    def _normalize_aliases(self, raw_aliases: Any, path: Path) -> tuple[str, ...]:
        if raw_aliases is None:
            return ()

        if not isinstance(raw_aliases, list):
            raise InvalidCapabilitySpecError(
                f"Capability '{self._safe_relpath(path)}' field 'aliases' must be a list if present."
            )

        normalized: list[str] = []
        for idx, item in enumerate(raw_aliases):
            if not isinstance(item, str) or not item:
                raise InvalidCapabilitySpecError(
                    f"Capability '{self._safe_relpath(path)}' field 'aliases[{idx}]' must be a non-empty string."
                )
            normalized.append(item)

        return tuple(normalized)

    def _require_non_empty_string(self, raw: dict[str, Any], key: str, path: Path) -> str:
        value = raw.get(key)
        if not isinstance(value, str) or not value:
            raise InvalidCapabilitySpecError(
                f"Capability '{self._safe_relpath(path)}' field '{key}' must be a non-empty string."
            )
        return value

    def _safe_relpath(self, path: Path) -> str:
        try:
            return path.relative_to(self.repo_root).as_posix()
        except ValueError:
            return path.as_posix()
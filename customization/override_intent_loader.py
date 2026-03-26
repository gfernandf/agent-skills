from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from runtime.binding_models import OverrideIntent
from runtime.errors import RuntimeErrorBase


class OverrideIntentLoadError(RuntimeErrorBase):
    """Raised when local override intents cannot be loaded."""


class OverrideIntentLoader:
    """
    Load user-declared override intents from:

        .agent-skills/overrides.yaml

    This file expresses local preference/override intent for one or more
    capabilities. It does not execute or activate bindings by itself.
    """

    def __init__(self, host_root: Path) -> None:
        self.host_root = host_root

    def load(self) -> list[OverrideIntent]:
        path = self.host_root / ".agent-skills" / "overrides.yaml"

        if not path.exists():
            return []

        try:
            with path.open("r", encoding="utf-8") as f:
                raw = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise OverrideIntentLoadError(
                f"Invalid YAML in '{path}'.",
                cause=e,
            ) from e
        except OSError as e:
            raise OverrideIntentLoadError(
                f"Could not read '{path}'.",
                cause=e,
            ) from e

        if raw is None:
            return []

        if not isinstance(raw, dict):
            raise OverrideIntentLoadError(f"File '{path}' must contain a mapping.")

        overrides = raw.get("overrides", [])

        if not isinstance(overrides, list):
            raise OverrideIntentLoadError(f"'overrides' in '{path}' must be a list.")

        intents: list[OverrideIntent] = []

        for idx, item in enumerate(overrides):
            intents.append(
                self._normalize_override(
                    raw=item,
                    source_file=str(path),
                    index=idx,
                )
            )

        return intents

    def _normalize_override(
        self,
        *,
        raw: Any,
        source_file: str,
        index: int,
    ) -> OverrideIntent:
        if not isinstance(raw, dict):
            raise OverrideIntentLoadError(
                f"Override at index {index} in '{source_file}' must be a mapping."
            )

        capabilities = raw.get("capabilities")
        binding_id = raw.get("binding")
        service_id = raw.get("service")
        mode = raw.get("mode", "replace")

        normalized_capabilities = self._normalize_capabilities(
            capabilities=capabilities,
            source_file=source_file,
            index=index,
        )

        if binding_id is not None and (
            not isinstance(binding_id, str) or not binding_id
        ):
            raise OverrideIntentLoadError(
                f"Override at index {index} in '{source_file}' has an invalid 'binding' value."
            )

        if service_id is not None and (
            not isinstance(service_id, str) or not service_id
        ):
            raise OverrideIntentLoadError(
                f"Override at index {index} in '{source_file}' has an invalid 'service' value."
            )

        if (binding_id is None and service_id is None) or (
            binding_id is not None and service_id is not None
        ):
            raise OverrideIntentLoadError(
                f"Override at index {index} in '{source_file}' must define exactly one of 'binding' or 'service'."
            )

        if not isinstance(mode, str) or mode not in {"replace", "prefer"}:
            raise OverrideIntentLoadError(
                f"Override at index {index} in '{source_file}' has invalid mode '{mode}'."
            )

        return OverrideIntent(
            capabilities=normalized_capabilities,
            binding_id=binding_id,
            service_id=service_id,
            mode=mode,
            source_file=source_file,
        )

    def _normalize_capabilities(
        self,
        *,
        capabilities: Any,
        source_file: str,
        index: int,
    ) -> tuple[str, ...]:
        if not isinstance(capabilities, list) or not capabilities:
            raise OverrideIntentLoadError(
                f"Override at index {index} in '{source_file}' must define a non-empty 'capabilities' list."
            )

        normalized: list[str] = []

        for cap_idx, capability_id in enumerate(capabilities):
            if not isinstance(capability_id, str) or not capability_id:
                raise OverrideIntentLoadError(
                    f"Override at index {index} in '{source_file}' has invalid capability at position {cap_idx}."
                )
            normalized.append(capability_id)

        return tuple(normalized)

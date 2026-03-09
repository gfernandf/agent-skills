from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from runtime.errors import RuntimeErrorBase


class BindingStateStoreError(RuntimeErrorBase):
    """Raised when active binding state cannot be loaded or persisted."""


class BindingStateStore:
    """
    Persist and retrieve the activated local binding map from:

        .agent-skills/active_bindings.json

    This file represents the resolved operational state used at execution time.
    """

    def __init__(self, host_root: Path) -> None:
        self.host_root = host_root
        self.path = self.host_root / ".agent-skills" / "active_bindings.json"

    def load_active_bindings(self) -> dict[str, str]:
        """
        Load the current capability -> binding_id map.

        If the file does not exist, return an empty mapping.
        """
        if not self.path.exists():
            return {}

        try:
            with self.path.open("r", encoding="utf-8") as f:
                raw = json.load(f)
        except json.JSONDecodeError as e:
            raise BindingStateStoreError(
                f"Invalid JSON in '{self.path}'.",
                cause=e,
            ) from e
        except OSError as e:
            raise BindingStateStoreError(
                f"Could not read '{self.path}'.",
                cause=e,
            ) from e

        if not isinstance(raw, dict):
            raise BindingStateStoreError(
                f"File '{self.path}' must contain an object mapping capability ids to binding ids."
            )

        normalized: dict[str, str] = {}

        for capability_id, binding_id in raw.items():
            if not isinstance(capability_id, str) or not capability_id:
                raise BindingStateStoreError(
                    f"File '{self.path}' contains an invalid capability id."
                )

            if not isinstance(binding_id, str) or not binding_id:
                raise BindingStateStoreError(
                    f"File '{self.path}' contains an invalid binding id for capability '{capability_id}'."
                )

            normalized[capability_id] = binding_id

        return normalized

    def save_active_bindings(self, bindings: dict[str, str]) -> None:
        """
        Persist the full capability -> binding_id map.

        The file is written deterministically with sorted keys to reduce noise in
        diffs and simplify inspection.
        """
        self._validate_bindings_mapping(bindings)

        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("w", encoding="utf-8", newline="\n") as f:
                json.dump(bindings, f, indent=2, sort_keys=True, ensure_ascii=False)
                f.write("\n")
        except OSError as e:
            raise BindingStateStoreError(
                f"Could not write '{self.path}'.",
                cause=e,
            ) from e

    def _validate_bindings_mapping(self, bindings: Any) -> None:
        if not isinstance(bindings, dict):
            raise BindingStateStoreError(
                "Active bindings state must be a mapping of capability ids to binding ids."
            )

        for capability_id, binding_id in bindings.items():
            if not isinstance(capability_id, str) or not capability_id:
                raise BindingStateStoreError(
                    "Active bindings state contains an invalid capability id."
                )

            if not isinstance(binding_id, str) or not binding_id:
                raise BindingStateStoreError(
                    f"Active bindings state contains an invalid binding id for capability '{capability_id}'."
                )
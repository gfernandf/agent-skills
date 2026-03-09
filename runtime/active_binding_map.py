from __future__ import annotations

from pathlib import Path

from customization.binding_state_store import BindingStateStore


class ActiveBindingMap:
    """
    Read-only runtime view over the locally activated binding selection.

    This is the execution-facing adapter for:

        .agent-skills/active_bindings.json

    It does not decide anything by itself. It only exposes the current
    capability -> binding_id mapping to the BindingResolver.
    """

    def __init__(self, host_root: Path | None = None) -> None:
        self.host_root = host_root
        self._state_store: BindingStateStore | None = None
        self._cache: dict[str, str] | None = None

        if self.host_root is not None:
            self._state_store = BindingStateStore(self.host_root)

    def get_active_binding_id(self, capability_id: str) -> str | None:
        """
        Return the locally activated binding id for a capability, if any.
        """
        if not isinstance(capability_id, str) or not capability_id:
            return None

        active = self._load()
        return active.get(capability_id)

    def list_active_bindings(self) -> dict[str, str]:
        """
        Return a copy of the full active binding map.
        """
        return dict(self._load())

    def refresh(self) -> None:
        """
        Drop the in-memory cache so the next read reflects persisted state.
        """
        self._cache = None

    def _load(self) -> dict[str, str]:
        if self._cache is not None:
            return self._cache

        if self._state_store is None:
            self._cache = {}
            return self._cache

        self._cache = self._state_store.load_active_bindings()
        return self._cache
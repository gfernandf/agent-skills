from __future__ import annotations

import pytest

from runtime.checkpoint import dict_to_state, state_to_dict
from runtime.execution_state import create_execution_state
from runtime.versioning import CURRENT_STATE_VERSION, is_state_version_compatible


def test_state_version_compatible_with_same_major() -> None:
    assert is_state_version_compatible("1.0.0", CURRENT_STATE_VERSION) is True
    assert is_state_version_compatible("1.3.9", CURRENT_STATE_VERSION) is True


def test_state_version_incompatible_with_cross_major() -> None:
    assert is_state_version_compatible("2.0.0", CURRENT_STATE_VERSION) is False


def test_checkpoint_restore_rejects_incompatible_state_version() -> None:
    state = create_execution_state("version.demo", {"x": 1}, trace_id="trace-v1")
    payload = state_to_dict(state)
    payload["state_version"] = "2.0.0"

    with pytest.raises(ValueError, match="Incompatible state_version"):
        dict_to_state(payload)

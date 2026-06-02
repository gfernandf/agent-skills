from __future__ import annotations

import re


CURRENT_STATE_VERSION = "1.0.0"


def _parse_semver(value: str | None) -> tuple[int, int, int] | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", text)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def is_state_version_compatible(
    serialized_state_version: str | None,
    runtime_state_version: str = CURRENT_STATE_VERSION,
) -> bool:
    serialized = _parse_semver(serialized_state_version)
    runtime = _parse_semver(runtime_state_version)
    if serialized is None or runtime is None:
        return False
    # Temporal-style baseline guardrail: reject cross-major state schemas.
    return serialized[0] == runtime[0]

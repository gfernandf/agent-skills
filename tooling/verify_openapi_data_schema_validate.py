#!/usr/bin/env python3
"""Compatibility wrapper for the generic OpenAPI verification harness."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    scenario_path = (
        ROOT / "tooling" / "openapi_scenarios" / "data.schema.validate.mock.json"
    )
    cmd = [
        sys.executable,
        str(ROOT / "tooling" / "verify_openapi_bindings.py"),
        "--scenario",
        str(scenario_path),
    ]
    completed = subprocess.run(cmd, check=False)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())

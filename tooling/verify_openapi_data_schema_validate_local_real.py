#!/usr/bin/env python3
"""Verify local real-service OpenAPI pilot for data.schema.validate."""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent


def _wait_for_health(url: str, timeout_seconds: float = 8.0) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            response = requests.get(url, timeout=1.0)
            if response.ok:
                return True
        except Exception:
            pass
        time.sleep(0.2)
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify local real OpenAPI pilot for data.schema.validate")
    parser.add_argument(
        "--service-running",
        action="store_true",
        help="Assume local provider is already running at 127.0.0.1:8780.",
    )
    args = parser.parse_args()

    service_proc = None
    try:
        if not args.service_running:
            service_cmd = [
                sys.executable,
                str(ROOT / "tooling" / "openapi_providers" / "data_schema_validate_service.py"),
                "--host",
                "127.0.0.1",
                "--port",
                "8780",
            ]
            service_proc = subprocess.Popen(service_cmd)

        if not _wait_for_health("http://127.0.0.1:8780/health"):
            print("Local provider did not become healthy in time.")
            return 1

        verify_cmd = [
            sys.executable,
            str(ROOT / "tooling" / "verify_openapi_bindings.py"),
            "--scenario",
            str(ROOT / "tooling" / "openapi_scenarios_real" / "data.schema.validate.local.json"),
        ]
        completed = subprocess.run(verify_cmd, check=False)
        return completed.returncode
    finally:
        if service_proc is not None:
            service_proc.terminate()
            try:
                service_proc.wait(timeout=3)
            except Exception:
                service_proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3

from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
REGISTRY_ROOT = ROOT.parent / "agent-skill-registry"


def _request_json(
    url: str,
    *,
    method: str = "GET",
    payload: dict | None = None,
    headers: dict | None = None,
) -> tuple[int, dict]:
    body = None
    request_headers = {"Content-Type": "application/json"}
    if headers:
        request_headers.update(headers)

    if payload is not None:
        body = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(url, data=body, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8")
            return resp.getcode(), json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8")
        parsed = json.loads(raw) if raw else {}
        return e.code, parsed


def main() -> int:
    api_key = "test-secret-key"
    server_proc = subprocess.Popen(
        [
            sys.executable,
            str(ROOT / "tooling" / "run_customer_http_api.py"),
            "--host",
            "127.0.0.1",
            "--port",
            "8085",
            "--runtime-root",
            str(ROOT),
            "--registry-root",
            str(REGISTRY_ROOT),
            "--api-key",
            api_key,
            "--rate-limit-requests",
            "3",
            "--rate-limit-window-seconds",
            "2",
        ]
    )

    try:
        time.sleep(0.8)

        # Unauthenticated path should still work.
        status, health = _request_json("http://127.0.0.1:8085/v1/health")
        if status != 200 or health.get("status") != "ok":
            raise RuntimeError("health endpoint failed expected unauthenticated access")

        # Protected route without key.
        status, body = _request_json(
            "http://127.0.0.1:8085/v1/skills/agent.plan-from-objective/describe",
            method="GET",
        )
        if status != 401:
            raise RuntimeError(f"expected 401 without api key, got {status}")
        if body.get("error", {}).get("code") != "unauthorized":
            raise RuntimeError("missing unauthorized error code")

        # Protected route with invalid key.
        status, body = _request_json(
            "http://127.0.0.1:8085/v1/skills/agent.plan-from-objective/describe",
            method="GET",
            headers={"x-api-key": "wrong-key"},
        )
        if status != 403:
            raise RuntimeError(f"expected 403 with wrong api key, got {status}")
        if body.get("error", {}).get("code") != "forbidden":
            raise RuntimeError("missing forbidden error code")

        # Valid request with valid key.
        status, desc = _request_json(
            "http://127.0.0.1:8085/v1/skills/agent.plan-from-objective/describe",
            method="GET",
            headers={"x-api-key": api_key},
        )
        if status != 200 or desc.get("id") != "agent.plan-from-objective":
            raise RuntimeError("authorized describe request failed")

        # Hit rate limit (3 allowed per 2 seconds, this is 4th protected request in window).
        for _ in range(3):
            _request_json(
                "http://127.0.0.1:8085/v1/skills/agent.plan-from-objective/describe",
                method="GET",
                headers={"x-api-key": api_key},
            )

        status, body = _request_json(
            "http://127.0.0.1:8085/v1/skills/agent.plan-from-objective/describe",
            method="GET",
            headers={"x-api-key": api_key},
        )
        if status != 429:
            raise RuntimeError(f"expected 429 when rate limited, got {status}")
        if body.get("error", {}).get("code") != "rate_limited":
            raise RuntimeError("missing rate_limited error code")

        print("Customer-facing HTTP controls verification passed.")
        return 0
    finally:
        server_proc.terminate()
        try:
            server_proc.wait(timeout=5)
        except Exception:
            server_proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())

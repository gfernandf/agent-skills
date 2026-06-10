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
    timeout_seconds: float = 20.0,
    attempts: int = 3,
    retry_delay_seconds: float = 0.5,
) -> tuple[int, dict]:
    body = None
    request_headers = {"Content-Type": "application/json"}
    if headers:
        request_headers.update(headers)

    if payload is not None:
        body = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(url, data=body, headers=request_headers, method=method)
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
                raw = resp.read().decode("utf-8")
                return resp.getcode(), json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8")
            parsed = json.loads(raw) if raw else {}
            return e.code, parsed
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = exc
            if attempt < attempts:
                time.sleep(retry_delay_seconds * attempt)
                continue
            raise RuntimeError(
                f"request failed after retries: method={method} url={url} error={exc}"
            ) from exc

    raise RuntimeError(
        f"request failed after retries: method={method} url={url} error={last_error}"
    )


def _wait_for_server_ready(base_url: str, *, timeout_seconds: float = 20.0) -> None:
    deadline = time.time() + timeout_seconds
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            status, body = _request_json(f"{base_url}/v1/health")
            if status == 200 and body.get("status") == "ok":
                return
        except Exception as exc:  # pragma: no cover - exercised in integration runs
            last_error = exc
        time.sleep(0.2)
    raise RuntimeError(f"server did not become ready at {base_url}: {last_error}")


def _pick_skill(base_url: str, api_key: str) -> str:
    status, payload = _request_json(
        f"{base_url}/v1/skills/list",
        method="GET",
        headers={"x-api-key": api_key},
    )
    if status != 200:
        raise RuntimeError(f"skills/list failed with status={status}")
    skills = payload.get("skills") if isinstance(payload, dict) else None
    if not isinstance(skills, list):
        raise RuntimeError("skills/list did not return a skills array")

    available = {
        item.get("id")
        for item in skills
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    preferred = [
        "agent.plan-and-route",
        "agent.execute-from-plan",
        "agent.orchestrate-from-prompt",
    ]
    for skill_id in preferred:
        if skill_id in available:
            return skill_id
    raise RuntimeError(f"none of preferred verification skills found: {preferred}")


def main() -> int:
    api_key = "test-secret-key"
    base_url = "http://127.0.0.1:8085"
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
        _wait_for_server_ready(base_url)
        skill_id = _pick_skill(base_url, api_key)

        # Unauthenticated path should still work.
        status, health = _request_json(f"{base_url}/v1/health")
        if status != 200 or health.get("status") != "ok":
            raise RuntimeError("health endpoint failed expected unauthenticated access")

        # Protected route without key.
        status, body = _request_json(
            f"{base_url}/v1/skills/{skill_id}/describe",
            method="GET",
        )
        if status != 401:
            raise RuntimeError(f"expected 401 without api key, got {status}")
        if body.get("error", {}).get("code") != "unauthorized":
            raise RuntimeError("missing unauthorized error code")

        # Protected route with invalid key.
        status, body = _request_json(
            f"{base_url}/v1/skills/{skill_id}/describe",
            method="GET",
            headers={"x-api-key": "wrong-key"},
        )
        if status not in {401, 403}:
            raise RuntimeError(f"expected 401/403 with wrong api key, got {status}")
        if body.get("error", {}).get("code") not in {"unauthorized", "forbidden"}:
            raise RuntimeError("missing unauthorized/forbidden error code")

        # Valid request with valid key.
        status, desc = _request_json(
            f"{base_url}/v1/skills/{skill_id}/describe",
            method="GET",
            headers={"x-api-key": api_key},
        )
        if status != 200 or desc.get("id") != skill_id:
            raise RuntimeError("authorized describe request failed")

        # Burst protected requests and assert we observe a 429 within bounded attempts.
        observed_rate_limit = False
        for _ in range(6):
            status, body = _request_json(
                f"{base_url}/v1/skills/{skill_id}/describe",
                method="GET",
                headers={"x-api-key": api_key},
            )
            if status == 429:
                observed_rate_limit = True
                if body.get("error", {}).get("code") != "rate_limited":
                    raise RuntimeError("missing rate_limited error code")
                break
            if status != 200:
                raise RuntimeError(
                    f"unexpected status during rate-limit burst: {status}"
                )

        if not observed_rate_limit:
            raise RuntimeError(
                "expected to observe 429 when rate limited, but none seen"
            )

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

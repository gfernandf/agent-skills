from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.error import URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SERVER_HOST = "127.0.0.1"
DEFAULT_SERVER_PORT = 8086
DEFAULT_WEBHOOK_PORT = 8091
DEFAULT_API_KEY = "test-secret-key"


def request_json(method: str, url: str, body: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> tuple[int, dict[str, Any]]:
    raw = b""
    req_headers = {"Content-Type": "application/json"}
    if headers:
        req_headers.update(headers)
    if body is not None:
        raw = json.dumps(body).encode("utf-8")
    req = Request(url, data=raw if body is not None else None, method=method, headers=req_headers)
    try:
        with urlopen(req, timeout=10) as resp:
            data = resp.read().decode("utf-8")
            return resp.status, (json.loads(data) if data else {})
    except HTTPError as e:
        data = e.read().decode("utf-8")
        try:
            parsed = json.loads(data) if data else {}
        except Exception:
            parsed = {"raw": data}
        return e.code, parsed
    except URLError as e:
        return 0, {"error": str(e)}


class _WebhookHandler(BaseHTTPRequestHandler):
    events: list[dict[str, Any]] = []

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length > 0 else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception:
            payload = {"raw": raw.decode("utf-8", errors="ignore")}
        _WebhookHandler.events.append(payload)
        self.send_response(204)
        self.end_headers()

    def log_message(self, fmt: str, *args: Any) -> None:
        return


def _wait_for_health(
    server_proc: subprocess.Popen[Any],
    base_url: str,
    timeout_s: int = 30,
) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if server_proc.poll() is not None:
            out, err = server_proc.communicate(timeout=2)
            raise RuntimeError(
                "Server process exited before becoming ready.\n"
                f"exit={server_proc.returncode}\n"
                f"stdout:\n{out}\n"
                f"stderr:\n{err}"
            )
        status, body = request_json("GET", f"{base_url}/v1/health")
        if status == 200 and body.get("status") == "ok":
            return
        time.sleep(0.5)
    raise RuntimeError("Server health endpoint did not become ready")


def _poll_run(
    run_id: str,
    base_url: str,
    api_key: str,
    timeout_s: int = 60,
) -> dict[str, Any]:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        status, body = request_json(
            "GET",
            f"{base_url}/run_status/{run_id}",
            headers={"x-api-key": api_key},
        )
        if status != 200:
            raise RuntimeError(f"run_status failed for {run_id}: {status} {body}")
        if body.get("status") in {"completed", "failed"}:
            return body
        time.sleep(0.5)
    raise RuntimeError(f"Run {run_id} did not reach terminal state")


def main() -> int:
    parser = argparse.ArgumentParser(description="Async HTTP E2E smoke test")
    parser.add_argument("--host", default=DEFAULT_SERVER_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_SERVER_PORT)
    parser.add_argument("--webhook-port", type=int, default=DEFAULT_WEBHOOK_PORT)
    parser.add_argument("--api-key", default=os.environ.get("CUSTOMER_API_KEY", DEFAULT_API_KEY))
    args = parser.parse_args()

    base_url = f"http://{args.host}:{args.port}"
    api_key = args.api_key

    webhook_server = ThreadingHTTPServer(("127.0.0.1", args.webhook_port), _WebhookHandler)
    webhook_thread = threading.Thread(target=webhook_server.serve_forever, daemon=True)
    webhook_thread.start()

    env = os.environ.copy()
    env["AGENT_SKILLS_WEBHOOKS_ALLOW_PRIVATE"] = "1"
    env["AGENT_SKILLS_WEBHOOKS_SKIP_URL_VALIDATION"] = "1"

    server_cmd = [
        sys.executable,
        str(ROOT / "tooling" / "run_customer_http_api.py"),
        "--host",
        args.host,
        "--port",
        str(args.port),
        "--runtime-root",
        str(ROOT),
        "--registry-root",
        str(ROOT.parent / "agent-skill-registry"),
        "--api-key",
        api_key,
        "--rate-limit-requests",
        "200",
        "--rate-limit-window-seconds",
        "60",
    ]

    server_proc = subprocess.Popen(server_cmd, env=env)

    try:
        _wait_for_health(server_proc, base_url)

        status, skills = request_json(
            "GET",
            f"{base_url}/v1/skills/list?limit=20",
            headers={"x-api-key": api_key},
        )
        if status != 200:
            raise RuntimeError(f"skills/list failed: {status} {skills}")

        skill_ids = [s.get("id") for s in skills.get("skills", []) if isinstance(s, dict)]
        preferred = ["agent.request.normalize", "agent.goal.interpret", "decision.make"]
        skill_id = next((s for s in preferred if s in skill_ids), None)
        if skill_id is None:
            if not skill_ids:
                raise RuntimeError("No skills found in /v1/skills/list")
            skill_id = skill_ids[0]

        status, wh = request_json(
            "POST",
            f"{base_url}/v1/webhooks",
            body={
                "url": f"http://127.0.0.1:{args.webhook_port}/cb",
                "events": ["run.completed", "run.failed"],
                "secret": "smoke-secret",
            },
            headers={"x-api-key": api_key},
        )
        if status != 201:
            raise RuntimeError(f"webhook register failed: {status} {wh}")

        status, launch = request_json(
            "POST",
            f"{base_url}/run_async",
            body={
                "skill_id": skill_id,
                "inputs": {
                    "user_message": "hola",
                    "goal": "smoke async",
                    "objective": "smoke async",
                    "context_items": [],
                },
            },
            headers={"x-api-key": api_key},
        )
        if status != 202 or "run_id" not in launch:
            raise RuntimeError(f"run_async failed: {status} {launch}")

        run1 = _poll_run(launch["run_id"], base_url, api_key)

        status, runs_all = request_json(
            "GET",
            f"{base_url}/v1/runs?limit=5&offset=0",
            headers={"x-api-key": api_key},
        )
        if status != 200 or "runs" not in runs_all or "pagination" not in runs_all:
            raise RuntimeError(f"runs list failed: {status} {runs_all}")

        status, _runs_completed = request_json(
            "GET",
            f"{base_url}/v1/runs?status=completed&limit=5",
            headers={"x-api-key": api_key},
        )
        if status != 200:
            raise RuntimeError(f"runs status filter failed: {status}")

        status, launch2 = request_json(
            "POST",
            f"{base_url}/run_async",
            body={
                "skill_id": skill_id,
                "inputs": {
                    "user_message": "hola de nuevo",
                    "goal": "smoke async cancel",
                    "objective": "smoke async cancel",
                    "context_items": [],
                },
            },
            headers={"x-api-key": api_key},
        )
        if status != 202 or "run_id" not in launch2:
            raise RuntimeError(f"second run_async failed: {status} {launch2}")

        status, canceled = request_json(
            "POST",
            f"{base_url}/run_cancel/{launch2['run_id']}",
            headers={"x-api-key": api_key},
        )
        if status != 200:
            raise RuntimeError(f"run_cancel failed: {status} {canceled}")

        run2 = _poll_run(launch2["run_id"], base_url, api_key)

        deadline = time.time() + 10
        while time.time() < deadline and not _WebhookHandler.events:
            time.sleep(0.2)

        if not _WebhookHandler.events:
            raise RuntimeError("No webhook events received")

        event_names = {evt.get("event") for evt in _WebhookHandler.events if isinstance(evt, dict)}
        if not ({"run.completed", "run.failed"} & event_names):
            raise RuntimeError(f"Unexpected webhook events: {sorted(event_names)}")

        print("PASS E2E")
        print(f"skill_id={skill_id}")
        print(f"run1={run1.get('status')} run_id={launch['run_id']}")
        print(f"run2={run2.get('status')} run_id={launch2['run_id']}")
        print(f"webhook_events={sorted(event_names)} total={len(_WebhookHandler.events)}")
        print(f"runs_page_size={len(runs_all.get('runs', []))}")
        return 0
    finally:
        webhook_server.shutdown()
        server_proc.terminate()
        try:
            server_proc.wait(timeout=10)
        except Exception:
            server_proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())

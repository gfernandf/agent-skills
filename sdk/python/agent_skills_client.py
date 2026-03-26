"""
Lightweight Python client for the agent-skills HTTP API.

Usage::

    from agent_skills_client import AgentSkillsClient

    client = AgentSkillsClient("http://localhost:8080", api_key="my-key")
    result = client.execute("text.content.generate", {"prompt": "Hello"})
    print(result)
"""

from __future__ import annotations

import json
import time
from typing import Any, Generator
from urllib.request import Request, urlopen
from urllib.error import HTTPError


class AgentSkillsClient:
    """Thin client for the agent-skills consumer-facing API."""

    def __init__(
        self, base_url: str = "http://localhost:8080", *, api_key: str | None = None
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def _headers(self) -> dict[str, str]:
        h: dict[str, str] = {"Content-Type": "application/json"}
        if self.api_key:
            h["x-api-key"] = self.api_key
        return h

    def _request(self, method: str, path: str, body: dict | None = None) -> Any:
        url = f"{self.base_url}{path}"
        data = json.dumps(body).encode() if body else None
        req = Request(url, data=data, headers=self._headers(), method=method)
        try:
            with urlopen(req) as resp:
                return json.loads(resp.read())
        except HTTPError as e:
            error_body = e.read().decode() if e.fp else ""
            raise APIError(e.code, error_body) from e

    # ── Core operations ──────────────────────────────────────────

    def health(self) -> dict:
        return self._request("GET", "/v1/health")

    def list_skills(self) -> dict:
        return self._request("GET", "/v1/skills/list")

    def describe(self, skill_id: str) -> dict:
        return self._request("GET", f"/v1/skills/{skill_id}/describe")

    def execute(self, skill_id: str, inputs: dict, **options: Any) -> dict:
        body: dict[str, Any] = {"inputs": inputs}
        if options:
            body["options"] = options
        return self._request("POST", f"/v1/skills/{skill_id}/execute", body)

    def discover(self, intent: str, *, limit: int = 10) -> dict:
        return self._request(
            "POST", "/v1/skills/discover", {"intent": intent, "limit": limit}
        )

    # ── Async execution ──────────────────────────────────────────

    def execute_async(self, skill_id: str, inputs: dict, **options: Any) -> dict:
        body: dict[str, Any] = {"inputs": inputs}
        if options:
            body["options"] = options
        return self._request("POST", f"/v1/skills/{skill_id}/execute/async", body)

    def get_run(self, run_id: str) -> dict:
        return self._request("GET", f"/v1/runs/{run_id}")

    def list_runs(self) -> dict:
        return self._request("GET", "/v1/runs")

    def wait_for_run(
        self, run_id: str, *, poll_interval: float = 1.0, timeout: float = 300
    ) -> dict:
        """Poll until a run completes or times out."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            run = self.get_run(run_id)
            if run.get("status") in ("completed", "failed"):
                return run
            time.sleep(poll_interval)
        raise TimeoutError(f"Run {run_id} did not complete within {timeout}s")

    # ── Streaming (SSE) ──────────────────────────────────────────

    def execute_stream(
        self, skill_id: str, inputs: dict, **options: Any
    ) -> Generator[dict, None, None]:
        """Yield parsed SSE events from a streaming execution."""
        body: dict[str, Any] = {"inputs": inputs}
        if options:
            body["options"] = options
        url = f"{self.base_url}/v1/skills/{skill_id}/execute/stream"
        data = json.dumps(body).encode()
        req = Request(url, data=data, headers=self._headers(), method="POST")
        with urlopen(req) as resp:
            event_type = ""
            for raw_line in resp:
                line = raw_line.decode("utf-8").rstrip("\n\r")
                if line.startswith("event:"):
                    event_type = line[6:].strip()
                elif line.startswith("data:"):
                    payload = line[5:].strip()
                    try:
                        parsed = json.loads(payload)
                    except json.JSONDecodeError:
                        parsed = payload
                    yield {"event": event_type, "data": parsed}
                    event_type = ""


class APIError(Exception):
    """Raised when the API returns a non-2xx response."""

    def __init__(self, status_code: int, body: str) -> None:
        self.status_code = status_code
        self.body = body
        super().__init__(f"HTTP {status_code}: {body[:200]}")

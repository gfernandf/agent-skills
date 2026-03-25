"""CrewAI tool adapter for agent-skills capabilities.

Wraps capabilities as CrewAI ``BaseTool`` instances so CrewAI agents can
use the agent-skills runtime as their tool backend.

Usage::

    from sdk.crewai_adapter import build_crewai_tools

    tools = build_crewai_tools(
        base_url="http://localhost:8080",
        capabilities=["text.content.summarize"],
    )
    # Pass ``tools`` to a CrewAI Agent.

Requires: ``crewai`` (``pip install crewai``)
"""
from __future__ import annotations

from typing import Any

import requests


def _call_capability(base_url: str, capability_id: str, payload: dict, api_key: str | None = None) -> dict:
    url = f"{base_url.rstrip('/')}/v1/capabilities/{capability_id}/execute"
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    resp = requests.post(url, json=payload, headers=headers, timeout=60)
    resp.raise_for_status()
    return resp.json()


def build_crewai_tools(
    base_url: str = "http://localhost:8080",
    capabilities: list[str] | None = None,
    api_key: str | None = None,
) -> list:
    """Build CrewAI-compatible tool instances for the given capabilities."""
    try:
        from crewai.tools import BaseTool as CrewAIBaseTool  # type: ignore[import-untyped]
    except ImportError as exc:
        raise ImportError(
            "crewai is required for the CrewAI adapter. "
            "Install it with: pip install crewai"
        ) from exc

    if capabilities is None:
        resp = requests.get(f"{base_url.rstrip('/')}/v1/capabilities", timeout=10)
        resp.raise_for_status()
        capabilities = [c["id"] for c in resp.json().get("capabilities", [])]

    tools = []
    for cap_id in capabilities:
        try:
            info = requests.get(f"{base_url.rstrip('/')}/v1/capabilities/{cap_id}", timeout=10)
            info.raise_for_status()
            meta = info.json()
            description = meta.get("description", cap_id)
        except Exception:
            description = cap_id

        _base_url = base_url
        _cap_id = cap_id
        _api_key = api_key

        class _Tool(CrewAIBaseTool):
            name: str = _cap_id.replace(".", "_")
            description: str = description  # type: ignore[assignment]

            def _run(self, **kwargs: Any) -> str:
                result = _call_capability(_base_url, _cap_id, kwargs, _api_key)
                return str(result)

        tools.append(_Tool())

    return tools

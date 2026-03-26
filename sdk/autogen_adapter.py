"""AutoGen tool adapter for agent-skills capabilities.

Wraps any capability exposed by the agent-skills HTTP API as an AutoGen
tool function so agents built with Microsoft AutoGen can invoke them.

Usage::

    from sdk.autogen_adapter import build_autogen_tools

    tools = build_autogen_tools(
        base_url="http://localhost:8080",
        capabilities=["text.content.summarize", "data.schema.validate"],
    )
    # Register tools with an AutoGen assistant agent.

Compatible with AutoGen 0.2+ (function-based tool registration).
"""

from __future__ import annotations

from typing import Any

import requests


def _call_capability(
    base_url: str,
    capability_id: str,
    payload: dict,
    api_key: str | None = None,
) -> dict:
    """POST to the agent-skills neutral API and return the result."""
    url = f"{base_url.rstrip('/')}/v1/capabilities/{capability_id}/execute"
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    resp = requests.post(url, json=payload, headers=headers, timeout=60)
    resp.raise_for_status()
    return resp.json()


def build_autogen_tools(
    base_url: str = "http://localhost:8080",
    capabilities: list[str] | None = None,
    api_key: str | None = None,
) -> list[dict[str, Any]]:
    """Build a list of AutoGen-compatible tool definitions.

    Each tool is a dict with ``name``, ``description``, and ``function``
    keys — the format accepted by ``register_function`` in AutoGen 0.2+.

    Parameters
    ----------
    base_url:
        Root URL of the agent-skills HTTP server.
    capabilities:
        Capability ids to expose.  If ``None``, the server's list endpoint
        is queried.
    api_key:
        Optional API key for authenticated instances.
    """
    if capabilities is None:
        resp = requests.get(
            f"{base_url.rstrip('/')}/v1/capabilities",
            timeout=10,
        )
        resp.raise_for_status()
        capabilities = [c["id"] for c in resp.json().get("capabilities", [])]

    tools: list[dict[str, Any]] = []
    for cap_id in capabilities:
        try:
            info = requests.get(
                f"{base_url.rstrip('/')}/v1/capabilities/{cap_id}",
                timeout=10,
            )
            info.raise_for_status()
            meta = info.json()
            description = meta.get("description", cap_id)
        except Exception:
            description = cap_id

        # Closure captures
        _base_url = base_url
        _cap_id = cap_id
        _api_key = api_key

        def _tool_fn(inputs: dict | None = None, **kwargs) -> dict:  # noqa: E731
            """Execute the agent-skills capability."""
            payload = {"inputs": inputs or kwargs}
            return _call_capability(_base_url, _cap_id, payload, _api_key)

        _tool_fn.__name__ = cap_id.replace(".", "_")
        _tool_fn.__doc__ = description

        tools.append(
            {
                "name": cap_id.replace(".", "_"),
                "description": description,
                "function": _tool_fn,
            }
        )

    return tools

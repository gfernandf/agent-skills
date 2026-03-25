"""Semantic Kernel plugin adapter for agent-skills capabilities.

Wraps any capability exposed by the agent-skills HTTP API as a Semantic
Kernel ``KernelFunction`` so agents built with Microsoft Semantic Kernel
can invoke them.

Usage::

    from sdk.semantic_kernel_adapter import build_sk_plugin

    plugin = build_sk_plugin(
        base_url="http://localhost:8080",
        capabilities=["text.content.summarize", "data.schema.validate"],
    )
    kernel.add_plugin(plugin, "agent_skills")

Requires: ``semantic-kernel`` (``pip install semantic-kernel``)
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


def build_sk_functions(
    base_url: str = "http://localhost:8080",
    capabilities: list[str] | None = None,
    api_key: str | None = None,
) -> list:
    """Build a list of Semantic Kernel ``KernelFunction`` objects.

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
    try:
        from semantic_kernel.functions import KernelFunction  # type: ignore[import-untyped]
        from semantic_kernel.functions.kernel_function_decorator import kernel_function  # type: ignore[import-untyped]
    except ImportError as exc:
        raise ImportError(
            "semantic-kernel is required for the SK adapter. "
            "Install it with: pip install semantic-kernel"
        ) from exc

    if capabilities is None:
        resp = requests.get(
            f"{base_url.rstrip('/')}/v1/capabilities",
            timeout=10,
        )
        resp.raise_for_status()
        capabilities = [c["id"] for c in resp.json().get("capabilities", [])]

    functions: list[KernelFunction] = []
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

        _base = base_url
        _cid = cap_id
        _key = api_key

        @kernel_function(
            name=cap_id.replace(".", "_"),
            description=description,
        )
        def _sk_fn(inputs: str = "{}") -> str:
            """Execute the agent-skills capability via HTTP."""
            import json
            payload = {"inputs": json.loads(inputs) if isinstance(inputs, str) else inputs}
            result = _call_capability(_base, _cid, payload, _key)
            return json.dumps(result, ensure_ascii=False)

        functions.append(_sk_fn)

    return functions


def build_sk_plugin(
    base_url: str = "http://localhost:8080",
    capabilities: list[str] | None = None,
    api_key: str | None = None,
    plugin_name: str = "agent_skills",
) -> Any:
    """Build a Semantic Kernel plugin containing all specified capabilities.

    Returns a ``KernelPlugin`` object ready for ``kernel.add_plugin()``.
    """
    try:
        from semantic_kernel.functions import KernelPlugin  # type: ignore[import-untyped]
    except ImportError as exc:
        raise ImportError(
            "semantic-kernel is required for the SK adapter. "
            "Install it with: pip install semantic-kernel"
        ) from exc

    functions = build_sk_functions(base_url, capabilities, api_key)
    return KernelPlugin(name=plugin_name, functions=functions)

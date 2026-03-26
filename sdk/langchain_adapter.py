"""LangChain tool adapter for agent-skills capabilities.

Wraps any capability exposed by the agent-skills HTTP API as a LangChain
``BaseTool`` so agents built with LangChain / LangGraph can invoke them.

Usage::

    from sdk.langchain_adapter import build_langchain_tools

    tools = build_langchain_tools(
        base_url="http://localhost:8080",
        capabilities=["text.content.summarize", "data.schema.validate"],
    )
    # Pass ``tools`` to an AgentExecutor or LangGraph node.

Requires: ``langchain-core`` (``pip install langchain-core``)
"""

from __future__ import annotations

from typing import Any, Optional

import requests


# Mapping from capability type strings to Python types for Pydantic fields.
_TYPE_MAP: dict[str, type] = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "array": list,
    "object": dict,
}


def _build_args_schema(cap_id: str, inputs_spec: dict) -> type | None:
    """Build a Pydantic BaseModel from capability input definitions.

    Returns ``None`` when ``pydantic`` is not available or *inputs_spec* is
    empty, which makes ``BaseTool`` fall back to free-form ``**kwargs``.
    """
    if not inputs_spec:
        return None
    try:
        from pydantic import BaseModel, Field  # type: ignore[import-untyped]
    except ImportError:
        return None

    fields: dict[str, Any] = {}
    for name, spec in inputs_spec.items():
        if isinstance(spec, dict):
            py_type = _TYPE_MAP.get(spec.get("type", "string"), str)
            required = spec.get("required", False)
            desc = spec.get("description", "")
            if required:
                fields[name] = (py_type, Field(description=desc))
            else:
                fields[name] = (Optional[py_type], Field(default=None, description=desc))
        else:
            fields[name] = (str, Field(default=None))

    # Create a dynamic Pydantic model
    model_name = cap_id.replace(".", "_") + "_Input"
    model = type(model_name, (BaseModel,), {"__annotations__": {k: v[0] for k, v in fields.items()}, **{k: v[1] for k, v in fields.items()}})
    return model


def _call_capability(
    base_url: str, capability_id: str, payload: dict, api_key: str | None = None
) -> dict:
    """POST to the agent-skills neutral API and return the result."""
    url = f"{base_url.rstrip('/')}/v1/capabilities/{capability_id}/execute"
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    resp = requests.post(url, json=payload, headers=headers, timeout=60)
    resp.raise_for_status()
    return resp.json()


def build_langchain_tools(
    base_url: str = "http://localhost:8080",
    capabilities: list[str] | None = None,
    api_key: str | None = None,
) -> list:
    """Build a list of LangChain ``BaseTool`` instances.

    Parameters
    ----------
    base_url:
        Root URL of the agent-skills HTTP server.
    capabilities:
        Capability ids to expose.  If ``None``, the server's discovery
        endpoint is queried.
    api_key:
        Optional API key for authenticated instances.

    Each tool gets an ``args_schema`` Pydantic model generated from the
    capability's input definitions, so LLM agents receive proper parameter
    names, types, and descriptions.
    """
    try:
        from langchain_core.tools import BaseTool  # type: ignore[import-untyped]
    except ImportError as exc:
        raise ImportError(
            "langchain-core is required for the LangChain adapter. "
            "Install it with: pip install langchain-core"
        ) from exc

    if capabilities is None:
        resp = requests.get(f"{base_url.rstrip('/')}/v1/capabilities", timeout=10)
        resp.raise_for_status()
        capabilities = [c["id"] for c in resp.json().get("capabilities", [])]

    tools: list[BaseTool] = []
    for cap_id in capabilities:
        # Fetch schema from discovery to build the tool description + args_schema
        inputs_spec: dict = {}
        try:
            info = requests.get(
                f"{base_url.rstrip('/')}/v1/capabilities/{cap_id}", timeout=10
            )
            info.raise_for_status()
            meta = info.json()
            description = meta.get("description", cap_id)
            inputs_spec = meta.get("inputs", {})
        except Exception:
            description = cap_id

        # Dynamic tool class
        _base_url = base_url
        _cap_id = cap_id
        _api_key = api_key
        _description = description
        _schema = _build_args_schema(cap_id, inputs_spec)

        class _CapabilityTool(BaseTool):
            name: str = _cap_id.replace(".", "_")
            description: str = _description  # type: ignore[assignment]
            if _schema is not None:
                args_schema: type = _schema  # type: ignore[assignment]

            def _run(self, **kwargs: Any) -> str:
                result = _call_capability(_base_url, _cap_id, kwargs, _api_key)
                return str(result)

            async def _arun(self, **kwargs: Any) -> str:
                # Fallback to sync — the HTTP call is short-lived
                return self._run(**kwargs)

        tools.append(_CapabilityTool())

    return tools

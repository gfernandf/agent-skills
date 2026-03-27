"""Embedded runtime — use agent-skills as a library, no HTTP server needed.

Provides in-process tool builders for LangChain, CrewAI, AutoGen, and
Semantic Kernel, plus a generic ``execute()`` function for direct use.

Quick start::

    from sdk.embedded import execute

    result = execute("text.summarize-plain-input", {"text": "Hello world.", "max_length": 20})
    print(result["summary"])

Framework integration (no server required)::

    from sdk.embedded import as_langchain_tools

    tools = as_langchain_tools(["text.content.summarize", "data.json.parse"])
    # Pass tools to any LangChain AgentExecutor or LangGraph node

All execution happens in-process via PythonCall / MCP in-process bindings.
No HTTP overhead, no server to manage.
"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Lazy singleton for the runtime engine
# ---------------------------------------------------------------------------

_engine = None
_capability_loader = None
_capability_executor = None


def _get_components():
    """Build or return the cached runtime components singleton."""
    global _engine, _capability_loader, _capability_executor
    if _engine is not None:
        return _engine, _capability_loader, _capability_executor

    import os

    from runtime.engine_factory import build_runtime_components

    # Auto-detect paths from environment or project layout
    project_root = Path(__file__).resolve().parent.parent
    registry_root = Path(
        os.environ.get("AGENT_SKILLS_REGISTRY_ROOT", project_root.parent / "agent-skill-registry")
    )
    runtime_root = Path(os.environ.get("AGENT_SKILLS_RUNTIME_ROOT", project_root))
    host_root = Path(os.environ.get("AGENT_SKILLS_HOST_ROOT", project_root))

    components = build_runtime_components(
        registry_root=registry_root,
        runtime_root=runtime_root,
        host_root=host_root,
        mcp_client_registry=None,
        local_skills_root=None,
    )
    _engine = components.engine
    _capability_loader = components.capability_loader
    _capability_executor = components.capability_executor
    return _engine, _capability_loader, _capability_executor


def reset():
    """Reset the cached engine (useful for testing or reconfiguration)."""
    global _engine, _capability_loader, _capability_executor
    _engine = None
    _capability_loader = None
    _capability_executor = None


# ---------------------------------------------------------------------------
# Direct execution API
# ---------------------------------------------------------------------------

def execute(
    skill_id: str,
    inputs: dict[str, Any],
    *,
    trace_id: str | None = None,
    channel: str = "embedded",
) -> dict[str, Any]:
    """Execute a skill in-process and return its outputs.

    >>> result = execute("text.summarize-plain-input", {"text": "Hello", "max_length": 20})
    >>> print(result["summary"])
    """
    from runtime.models import ExecutionRequest

    engine, _, _ = _get_components()
    req = ExecutionRequest(skill_id=skill_id, inputs=inputs, trace_id=trace_id, channel=channel)
    result = engine.execute(req)
    if result.status != "completed":
        error = getattr(result, "error", None) or result.status
        raise RuntimeError(f"Skill {skill_id} failed: {error}")
    return dict(result.outputs) if result.outputs else {}


def execute_capability(
    capability_id: str,
    inputs: dict[str, Any],
) -> dict[str, Any]:
    """Execute a single capability directly (no skill wrapper needed).

    >>> result = execute_capability("text.content.summarize", {"text": "Hello world", "max_length": 20})
    """
    _, cap_loader, cap_executor = _get_components()
    cap = cap_loader.get_capability(capability_id)
    raw = cap_executor.execute(cap, inputs)
    if isinstance(raw, tuple):
        raw = raw[0]
    return dict(raw) if isinstance(raw, dict) else {"result": raw}


def list_capabilities() -> list[dict[str, Any]]:
    """List all available capabilities with their metadata."""
    _, cap_loader, _ = _get_components()
    caps = cap_loader.get_all_capabilities()
    result = []
    for cap_id, cap in sorted(caps.items()):
        result.append({
            "id": cap_id,
            "description": getattr(cap, "description", ""),
            "inputs": {k: _field_to_dict(v) for k, v in (getattr(cap, "inputs", {}) or {}).items()},
            "outputs": {k: _field_to_dict(v) for k, v in (getattr(cap, "outputs", {}) or {}).items()},
        })
    return result


def list_skills() -> list[dict[str, str]]:
    """List all available skills."""
    engine, _, _ = _get_components()
    loader = engine.skill_loader
    # CompositeSkillLoader or YamlSkillLoader — both have _skill_index (or composites)
    skill_ids: list[str] = []
    if hasattr(loader, "_loaders"):
        for sub in loader._loaders:
            if sub._skill_index is None:
                sub._skill_index = sub._build_skill_index()
            skill_ids.extend(sub._skill_index.keys())
    else:
        if loader._skill_index is None:
            loader._skill_index = loader._build_skill_index()
        skill_ids = list(loader._skill_index.keys())

    result = []
    for sid in sorted(set(skill_ids)):
        try:
            skill = loader.get_skill(sid)
            result.append({
                "id": sid,
                "name": getattr(skill, "name", ""),
                "description": getattr(skill, "description", ""),
            })
        except Exception:
            result.append({"id": sid, "name": "", "description": ""})
    return result


def _field_to_dict(field: Any) -> dict[str, Any]:
    if isinstance(field, dict):
        return field
    return {
        "type": getattr(field, "type", "string"),
        "required": getattr(field, "required", False),
        "description": getattr(field, "description", ""),
    }


# ---------------------------------------------------------------------------
# Framework adapters — in-process (no HTTP)
# ---------------------------------------------------------------------------

def _make_capability_fn(cap_id: str) -> callable:
    """Create a callable that executes a capability in-process."""
    def _execute(**kwargs: Any) -> dict[str, Any]:
        return execute_capability(cap_id, kwargs)
    _execute.__name__ = cap_id.replace(".", "_")
    _execute.__doc__ = f"Execute capability {cap_id} via agent-skills embedded runtime."
    return _execute


def _resolve_capabilities(capabilities: list[str] | None) -> list[dict[str, Any]]:
    """Resolve the capability list — if None, return all available."""
    all_caps = list_capabilities()
    if capabilities is None:
        return all_caps
    cap_map = {c["id"]: c for c in all_caps}
    return [cap_map[cid] for cid in capabilities if cid in cap_map]


def as_langchain_tools(
    capabilities: list[str] | None = None,
) -> list:
    """Build LangChain BaseTool instances backed by the embedded runtime.

    No HTTP server needed — capabilities execute in-process.

    >>> tools = as_langchain_tools(["text.content.summarize"])
    >>> result = tools[0].invoke({"text": "Hello world", "max_length": 20})
    """
    try:
        from langchain_core.tools import BaseTool
    except ImportError as exc:
        raise ImportError(
            "langchain-core is required. Install: pip install langchain-core"
        ) from exc

    caps = _resolve_capabilities(capabilities)
    tools: list[BaseTool] = []

    for cap_info in caps:
        cap_id = cap_info["id"]
        description = cap_info.get("description", cap_id)
        fn = _make_capability_fn(cap_id)

        # Build args schema if pydantic is available
        schema = _try_build_pydantic_schema(cap_id, cap_info.get("inputs", {}))

        _cap_id = cap_id
        _desc = description
        _fn = fn
        _schema = schema

        class _Tool(BaseTool):
            name: str = _cap_id.replace(".", "_")
            description: str = _desc

            def _run(self, **kwargs: Any) -> str:
                return str(_fn(**kwargs))

            async def _arun(self, **kwargs: Any) -> str:
                return self._run(**kwargs)

        if _schema is not None:
            _Tool.args_schema = _schema

        tools.append(_Tool())

    return tools


def as_crewai_tools(
    capabilities: list[str] | None = None,
) -> list:
    """Build CrewAI BaseTool instances backed by the embedded runtime.

    >>> tools = as_crewai_tools(["text.content.summarize"])
    """
    try:
        from crewai.tools import BaseTool as CrewBaseTool
    except ImportError as exc:
        raise ImportError(
            "crewai is required. Install: pip install crewai"
        ) from exc

    caps = _resolve_capabilities(capabilities)
    tools = []

    for cap_info in caps:
        cap_id = cap_info["id"]
        description = cap_info.get("description", cap_id)
        fn = _make_capability_fn(cap_id)

        _cap_id = cap_id
        _desc = description
        _fn = fn

        class _Tool(CrewBaseTool):
            name: str = _cap_id.replace(".", "_")
            description: str = _desc

            def _run(self, **kwargs: Any) -> str:
                return str(_fn(**kwargs))

        tools.append(_Tool())

    return tools


def as_autogen_tools(
    capabilities: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Build AutoGen-compatible tool dicts backed by the embedded runtime.

    Returns list of ``{"name": ..., "description": ..., "function": ...}``
    compatible with AutoGen 0.2+ tool registration.

    >>> tools = as_autogen_tools(["text.content.summarize"])
    """
    caps = _resolve_capabilities(capabilities)
    tools = []

    for cap_info in caps:
        cap_id = cap_info["id"]
        fn = _make_capability_fn(cap_id)
        tools.append({
            "name": cap_id.replace(".", "_"),
            "description": cap_info.get("description", cap_id),
            "function": fn,
        })

    return tools


def as_semantic_kernel_functions(
    capabilities: list[str] | None = None,
) -> list:
    """Build Semantic Kernel KernelFunction objects backed by the embedded runtime.

    >>> functions = as_semantic_kernel_functions(["text.content.summarize"])
    """
    try:
        from semantic_kernel.functions import KernelFunction
        from semantic_kernel import KernelPlugin
    except ImportError as exc:
        raise ImportError(
            "semantic-kernel is required. Install: pip install semantic-kernel"
        ) from exc

    caps = _resolve_capabilities(capabilities)
    functions = []

    for cap_info in caps:
        cap_id = cap_info["id"]
        fn = _make_capability_fn(cap_id)
        kf = KernelFunction.from_native_method(fn, plugin_name="agent_skills")
        functions.append(kf)

    return functions


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TYPE_MAP: dict[str, type] = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "array": list,
    "object": dict,
}


def _try_build_pydantic_schema(cap_id: str, inputs_spec: dict) -> type | None:
    """Try to build a Pydantic model for a capability's inputs."""
    if not inputs_spec:
        return None
    try:
        from pydantic import Field, create_model

        fields = {}
        for name, spec in inputs_spec.items():
            ftype = _TYPE_MAP.get(spec.get("type", "string"), Any)
            required = spec.get("required", False)
            desc = spec.get("description", "")
            if required:
                fields[name] = (ftype, Field(description=desc))
            else:
                fields[name] = (ftype | None, Field(default=None, description=desc))

        return create_model(f"{cap_id.replace('.', '_')}_Input", **fields)
    except Exception:
        return None

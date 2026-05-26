"""Embedded runtime — use agent-skills as a library, no HTTP server needed.

Provides in-process tool builders for LangChain, CrewAI, AutoGen,
Semantic Kernel, and native LLM provider SDKs (Anthropic, OpenAI, Gemini),
plus a generic ``execute()`` function for direct use.

Quick start::

    from sdk import execute

    result = execute("text.summarize-plain-input", {"text": "Hello world.", "max_length": 20})
    print(result["summary"])

Framework integration (no server required)::

    from sdk import as_langchain_tools

    tools = as_langchain_tools(["text.content.summarize", "data.json.parse"])
    # Pass tools to any LangChain AgentExecutor or LangGraph node

Native LLM provider integration::

    from sdk import as_anthropic_tools, execute_anthropic_tool_call

    tools = as_anthropic_tools()  # ready for client.messages.create(tools=tools)
    # After receiving a tool_use block from Claude:
    result = execute_anthropic_tool_call(tool_name, tool_input)

All execution happens in-process via PythonCall / MCP in-process bindings.
No HTTP overhead, no server to manage.
"""

from __future__ import annotations

import json
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
        os.environ.get(
            "AGENT_SKILLS_REGISTRY_ROOT", project_root.parent / "agent-skill-registry"
        )
    )
    if not registry_root.exists():
        raise RuntimeError(
            f"agent-skill-registry not found at {registry_root}. "
            "Clone it alongside agent-skills:\n"
            "  git clone https://github.com/gfernandf/agent-skill-registry.git\n"
            "Or set AGENT_SKILLS_REGISTRY_ROOT to the correct path."
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

    >>> result = execute("text.summarize-plain-input", {"text": "Hello world"})
    >>> print(result["result"])
    """
    from runtime.models import ExecutionRequest

    engine, _, _ = _get_components()
    skill = engine.skill_loader.get_skill(skill_id)
    req = ExecutionRequest(
        skill_id=skill_id, inputs=inputs, trace_id=trace_id, channel=channel
    )
    try:
        result = engine.execute(req)
    except Exception as exc:
        code = _classify_error(exc)
        raise RuntimeError(
            f"Skill '{skill_id}' execution failed [{code}]: {exc}"
        ) from exc
    if result.status != "completed":
        msg = getattr(result, "error_message", None) or result.status
        raise RuntimeError(
            f"Skill '{skill_id}' finished with status '{result.status}': {msg}"
        )
    raw_outputs = dict(result.outputs) if result.outputs else {}
    return _normalize_outputs_to_skill_contract(skill, raw_outputs)


def _build_skill_execution_meta(result) -> dict[str, Any]:
    """Build a diagnostics block from an execution result's step_results."""
    step_diagnostics: list[dict[str, Any]] = []
    fallback_steps: list[dict[str, Any]] = []
    failed_steps_count = 0

    for step_id, step_result in result.state.step_results.items():
        attempts = step_result.binding_attempts or []
        failed_attempts = [
            a for a in attempts if isinstance(a, dict) and a.get("status") == "failed"
        ]
        attempts_count = step_result.attempts_count
        if not isinstance(attempts_count, int) or attempts_count < 1:
            attempts_count = max(len(attempts), 1)

        status = step_result.status or "unknown"
        if status != "completed":
            failed_steps_count += 1

        diagnostic: dict[str, Any] = {
            "step_id": step_id,
            "uses": step_result.uses,
            "status": status,
            "duration_ms": step_result.latency_ms if step_result.latency_ms is not None else 0,
            "binding_id": step_result.binding_id,
            "service_id": step_result.service_id,
            "primary_binding_id": step_result.primary_binding_id,
            "fallback_used": bool(step_result.fallback_used),
            "attempts_count": attempts_count,
        }
        if failed_attempts:
            diagnostic["attempt_failures"] = [
                {
                    "binding_id": a.get("binding_id"),
                    "error_type": a.get("error_type"),
                    "error_message": a.get("error_message"),
                }
                for a in failed_attempts
            ]
        step_diagnostics.append(diagnostic)
        if diagnostic["fallback_used"]:
            fallback_steps.append(diagnostic)

    steps_count = len(step_diagnostics)
    # Reconcile fallback_used with step_diagnostics while preserving uncertainty.
    # If diagnostics are missing and the engine does not provide an explicit
    # fallback flag, fallback_used remains unknown (None) instead of being forced.
    result_level_fallback_raw = getattr(result, "fallback_used", None)
    result_level_fallback: bool | None
    if isinstance(result_level_fallback_raw, bool):
        result_level_fallback = result_level_fallback_raw
    else:
        result_level_fallback = None

    if fallback_steps:
        derived_fallback_used: bool | None = True
    elif result_level_fallback is not None:
        derived_fallback_used = result_level_fallback
    else:
        derived_fallback_used = None
    # Count steps affected by fallback OR degraded/failed execution.
    affected_steps_count = sum(
        1
        for step in step_diagnostics
        if isinstance(step, dict)
        and (
            bool(step.get("fallback_used"))
            or step.get("status") in {"failed", "degraded", "skipped"}
        )
    )
    derived_fallback_count: int | None = max(len(fallback_steps), affected_steps_count)
    if result_level_fallback is True and not fallback_steps:
        # Fallback detected at engine level but no per-step record available.
        # Report it honestly rather than hiding it behind 0 steps.
        derived_fallback_count = 1  # at least 1 fallback step occurred

    execution_warnings: list[str] = []

    if steps_count == 0:
        trace_completeness = "none"
        execution_warnings.append(
            "No step diagnostics were captured; execution trace is not fully auditable."
        )
        # Without diagnostics, do not claim either clean run or fallback unless
        # runtime explicitly reported it.
        if derived_fallback_used is None:
            derived_fallback_count = None
    else:
        trace_completeness = "full"
        if derived_fallback_used is None:
            # With concrete step diagnostics, fallback status must be explicit.
            derived_fallback_used = False
        if failed_steps_count > 0:
            trace_completeness = "partial"
            execution_warnings.append(
                "One or more steps failed/degraded; trace is partial."
            )

    if derived_fallback_used is True and (
        not isinstance(derived_fallback_count, int) or derived_fallback_count < 1
    ):
        derived_fallback_count = 1

    retries_used = sum(
        max(int(step.get("attempts_count", 1)) - 1, 0)
        for step in step_diagnostics
        if isinstance(step, dict)
    )
    capabilities_executed = [
        step.get("uses")
        for step in step_diagnostics
        if isinstance(step, dict) and isinstance(step.get("uses"), str)
    ]
    # Preserve execution order but keep unique values.
    capabilities_executed = list(dict.fromkeys(capabilities_executed))

    fallback_severity = _classify_fallback_severity(
        step_diagnostics=step_diagnostics,
        fallback_steps_count=derived_fallback_count,
        steps_count=steps_count,
        failed_steps_count=failed_steps_count,
    )
    execution_health = _classify_execution_health(
        status=result.status,
        failed_steps_count=failed_steps_count,
        steps_count=steps_count,
        fallback_severity=fallback_severity,
        trace_completeness=trace_completeness,
    )

    return {
        "skill_id": result.skill_id,
        "trace_id": result.state.trace_id,
        "status": result.status,
        "steps_count": steps_count,
        "completed_steps_count": max(steps_count - failed_steps_count, 0),
        "failed_steps_count": failed_steps_count,
        "fallback_used": derived_fallback_used,
        "fallback_steps_count": derived_fallback_count,
        "fallback_severity": fallback_severity,
        "fallback_steps": fallback_steps,
        "step_diagnostics": step_diagnostics,
        "capabilities_executed": capabilities_executed,
        "retries_used": retries_used,
        "trace_completeness": trace_completeness,
        "execution_warnings": execution_warnings,
        "execution_health": execution_health,
    }


def _classify_fallback_severity(
    *,
    step_diagnostics: list[dict[str, Any]],
    fallback_steps_count: int,
    steps_count: int,
    failed_steps_count: int,
) -> dict[str, Any]:
    if fallback_steps_count <= 0:
        return {
            "level": "none",
            "message": "Execution completed successfully.",
        }

    ratio = fallback_steps_count / max(steps_count, 1)
    critical_uses = {
        "eval.option.analyze",
        "eval.option.score",
        "decision.option.justify",
    }
    critical_fallback = any(
        bool(step.get("fallback_used")) and step.get("uses") in critical_uses
        for step in step_diagnostics
        if isinstance(step, dict)
    )
    scoring_completed = any(
        step.get("uses") == "eval.option.score" and step.get("status") == "completed"
        for step in step_diagnostics
        if isinstance(step, dict)
    )
    retries_exhausted = any(
        step.get("status") != "completed" and int(step.get("attempts_count", 1)) > 1
        for step in step_diagnostics
        if isinstance(step, dict)
    )
    fallback_steps = [
        step for step in step_diagnostics
        if isinstance(step, dict) and bool(step.get("fallback_used"))
    ]
    justify_only_fallback = (
        fallback_steps_count == 1
        and len(fallback_steps) == 1
        and fallback_steps[0].get("step_id") == "justify_decision"
        and fallback_steps[0].get("uses") == "decision.option.justify"
    )

    if failed_steps_count > 0 or (critical_fallback and not scoring_completed):
        return {
            "level": "severe",
            "message": (
                "Execution reliability significantly reduced. "
                "Recommendation should be treated cautiously."
            ),
        }

    if justify_only_fallback and not retries_exhausted:
        return {
            "level": "minor",
            "message": (
                "Execution completed with minor fallback in justify_decision only. "
                "Recommendation remains reliable."
            ),
        }

    if critical_fallback or ratio >= 0.20 or retries_exhausted:
        return {
            "level": "moderate",
            "message": (
                "Execution completed with moderate degradation. "
                "Treat recommendation with some caution."
            ),
        }

    return {
        "level": "minor",
        "message": (
            "Execution completed with minor fallback in non-critical steps. "
            "Recommendation remains reliable."
        ),
    }


def _classify_execution_health(
    *,
    status: str,
    failed_steps_count: int,
    steps_count: int,
    fallback_severity: dict[str, Any],
    trace_completeness: str,
) -> str:
    if status != "completed":
        return "failed"
    if steps_count == 0 or failed_steps_count >= steps_count:
        return "failed"
    if failed_steps_count > 0:
        return "partial"
    if trace_completeness != "full":
        return "degraded"
    severity_level = fallback_severity.get("level") if isinstance(fallback_severity, dict) else None
    if severity_level in {"moderate", "severe"}:
        return "degraded"
    return "healthy"


def apply_execution_reliability_confidence_calibration(
    *,
    skill_id: str,
    outputs: dict[str, Any],
    meta: dict[str, Any],
) -> dict[str, Any]:
    """Apply fallback-aware confidence caps as the final runtime step.

    Rules:
    - minor fallback: cap score to 0.69 and level to at most medium.
    - moderate fallback: cap score to 0.65 and level to at most medium.
    - severe fallback: cap score to 0.40 and level to low.

    Adds ``execution_reliability_adjustment`` to outputs when score is adjusted.
    """
    # Reuse the same fallback-aware confidence policy for direct execution of
    # the decision justification capability to keep behavior consistent across
    # skill and capability entrypoints.
    if skill_id not in {"decision.make", "decision.option.justify"}:
        return outputs
    if not isinstance(outputs, dict) or not isinstance(meta, dict):
        return outputs

    if not bool(meta.get("fallback_used", False)):
        return outputs

    raw_score = outputs.get("confidence_score")
    try:
        score = float(raw_score)
    except Exception:
        return outputs

    severity = meta.get("fallback_severity")
    level = None
    if isinstance(severity, dict):
        level = severity.get("level")
    if not isinstance(level, str) or not level:
        level = "moderate"
    level = level.strip().lower()

    cap_by_level = {
        "minor": 0.69,
        "moderate": 0.65,
        "severe": 0.40,
    }
    cap = cap_by_level.get(level)
    if cap is None:
        cap = 0.65

    adjusted = min(score, cap)
    if adjusted != score:
        reason = "fallback used"
        fallback_steps = meta.get("fallback_steps")
        if isinstance(fallback_steps, list) and len(fallback_steps) == 1:
            step = fallback_steps[0]
            if isinstance(step, dict) and isinstance(step.get("step_id"), str):
                reason = f"fallback used in {step['step_id']}"

        outputs["execution_reliability_adjustment"] = {
            "raw_confidence_score": score,
            "adjusted_confidence_score": adjusted,
            "reason": reason,
        }
        outputs["confidence_score"] = adjusted

    confidence_level = outputs.get("confidence_level")
    if not isinstance(confidence_level, str):
        confidence_level = ""
    confidence_level = confidence_level.strip().lower()

    final_score = outputs.get("confidence_score")
    try:
        final_score_f = float(final_score)
    except Exception:
        final_score_f = adjusted

    if level == "severe":
        outputs["confidence_level"] = "low"
    elif final_score_f <= 0.70 and confidence_level == "high":
        outputs["confidence_level"] = "medium"

    return outputs


def execute_with_meta(
    skill_id: str,
    inputs: dict[str, Any],
    *,
    trace_id: str | None = None,
    channel: str = "embedded",
) -> dict[str, Any]:
    """Execute a skill and return outputs together with binding/fallback diagnostics.

    Returns a dict with ``outputs`` (the normal skill outputs) and ``meta``
    (binding diagnostics per step including fallback causes).
    """
    from runtime.models import ExecutionRequest

    engine, _, _ = _get_components()
    skill = engine.skill_loader.get_skill(skill_id)
    req = ExecutionRequest(
        skill_id=skill_id, inputs=inputs, trace_id=trace_id, channel=channel
    )
    try:
        result = engine.execute(req)
    except Exception as exc:
        code = _classify_error(exc)
        raise RuntimeError(
            f"Skill '{skill_id}' execution failed [{code}]: {exc}"
        ) from exc
    if result.status != "completed":
        msg = getattr(result, "error_message", None) or result.status
        raise RuntimeError(
            f"Skill '{skill_id}' finished with status '{result.status}': {msg}"
        )

    raw_outputs = dict(result.outputs) if result.outputs else {}
    meta = _build_skill_execution_meta(result)
    outputs = _normalize_outputs_to_skill_contract(skill, raw_outputs)
    outputs = apply_execution_reliability_confidence_calibration(
        skill_id=skill_id,
        outputs=outputs,
        meta=meta,
    )
    return {
        "outputs": outputs,
        "meta": meta,
    }


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
    meta: dict[str, Any] = {}
    if isinstance(raw, tuple):
        raw, raw_meta = raw
        if isinstance(raw_meta, dict):
            meta = raw_meta

    outputs = dict(raw) if isinstance(raw, dict) else {"result": raw}
    outputs = apply_execution_reliability_confidence_calibration(
        skill_id=capability_id,
        outputs=outputs,
        meta=meta,
    )
    return outputs


def list_capabilities() -> list[dict[str, Any]]:
    """List all available capabilities with their metadata."""
    _, cap_loader, _ = _get_components()
    caps = cap_loader.get_all_capabilities()
    result = []
    for cap_id, cap in sorted(caps.items()):
        result.append(
            {
                "id": cap_id,
                "description": getattr(cap, "description", ""),
                "inputs": {
                    k: _field_to_dict(v)
                    for k, v in (getattr(cap, "inputs", {}) or {}).items()
                },
                "outputs": {
                    k: _field_to_dict(v)
                    for k, v in (getattr(cap, "outputs", {}) or {}).items()
                },
            }
        )
    return result


def list_skills() -> list[dict[str, Any]]:
    """List all available skills with contract metadata."""
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
            result.append(
                {
                    "id": sid,
                    "name": getattr(skill, "name", ""),
                    "description": getattr(skill, "description", ""),
                    "inputs": {
                        k: _field_to_dict(v)
                        for k, v in (getattr(skill, "inputs", {}) or {}).items()
                    },
                    "outputs": {
                        k: _field_to_dict(v)
                        for k, v in (getattr(skill, "outputs", {}) or {}).items()
                    },
                }
            )
        except Exception:
            result.append(
                {
                    "id": sid,
                    "name": "",
                    "description": "",
                    "inputs": {},
                    "outputs": {},
                }
            )
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
        raise ImportError("crewai is required. Install: pip install crewai") from exc

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
        tools.append(
            {
                "name": cap_id.replace(".", "_"),
                "description": cap_info.get("description", cap_id),
                "function": fn,
            }
        )

    return tools


def as_semantic_kernel_functions(
    capabilities: list[str] | None = None,
) -> list:
    """Build Semantic Kernel KernelFunction objects backed by the embedded runtime.

    >>> functions = as_semantic_kernel_functions(["text.content.summarize"])
    """
    try:
        from semantic_kernel.functions import KernelFunction
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
# Native LLM provider adapters — in-process (no HTTP, no framework deps)
# ---------------------------------------------------------------------------


def as_anthropic_tools(
    capabilities: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Build Anthropic-compatible tool definitions for the Messages API.

    Returns a list of tool dicts ready to pass as ``tools=`` to
    ``client.messages.create()``.  No Anthropic SDK dependency required —
    only plain dicts are returned.

    Each tool dict has the shape::

        {
            "name": "text_content_summarize",
            "description": "Produce a condensed version of text ...",
            "input_schema": { "type": "object", "properties": {...}, "required": [...] }
        }

    Usage::

        from sdk.embedded import as_anthropic_tools, execute_anthropic_tool_call
        import anthropic

        client = anthropic.Anthropic()
        tools = as_anthropic_tools()  # or as_anthropic_tools(["text.content.summarize"])

        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            messages=[{"role": "user", "content": "Summarize this: ..."}],
            tools=tools,
        )

        # Process tool_use blocks in the response:
        for block in response.content:
            if block.type == "tool_use":
                result = execute_anthropic_tool_call(block.name, block.input)

    Args:
        capabilities: Optional list of capability IDs to expose.  If ``None``,
                      all runtime capabilities are included.

    Returns:
        List of Anthropic tool definition dicts.
    """
    caps = _resolve_capabilities(capabilities)
    tools: list[dict[str, Any]] = []

    for cap_info in caps:
        tools.append(
            {
                "name": cap_info["id"].replace(".", "_"),
                "description": cap_info.get("description", cap_info["id"]),
                "input_schema": _build_json_schema(cap_info),
            }
        )

    return tools


def execute_anthropic_tool_call(
    tool_name: str,
    tool_input: dict[str, Any],
) -> str:
    """Execute an Anthropic tool_use call and return the result as JSON string.

    Designed to be called when processing ``tool_use`` content blocks from
    Claude's response.  The return value is a JSON string ready to be sent
    back as a ``tool_result`` content block.

    Args:
        tool_name: The tool name from the ``tool_use`` block (underscored).
        tool_input: The input dict from the ``tool_use`` block.

    Returns:
        JSON string of the execution result (or error).

    Usage::

        result_json = execute_anthropic_tool_call(block.name, block.input)
        # Send back: {"type": "tool_result", "tool_use_id": block.id, "content": result_json}
    """
    # Convert underscored name back to dotted capability ID
    cap_id = tool_name.replace("_", ".")
    try:
        result = execute_capability(cap_id, tool_input)
        return json.dumps(result, default=str)
    except Exception as exc:
        return json.dumps({"error": str(exc), "code": _classify_error(exc)})


def as_openai_tools(
    capabilities: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Build OpenAI-compatible tool definitions for the Chat Completions API.

    Returns a list of tool dicts ready to pass as ``tools=`` to
    ``client.chat.completions.create()``.  No OpenAI SDK dependency required.

    Each tool dict has the shape::

        {
            "type": "function",
            "function": {
                "name": "text_content_summarize",
                "description": "Produce a condensed version of text ...",
                "parameters": { "type": "object", "properties": {...}, "required": [...] }
            }
        }

    Usage::

        from sdk.embedded import as_openai_tools, execute_openai_tool_call
        from openai import OpenAI

        client = OpenAI()
        tools = as_openai_tools()

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": "Summarize this: ..."}],
            tools=tools,
        )

        # Process tool calls in the response:
        for tool_call in response.choices[0].message.tool_calls or []:
            result = execute_openai_tool_call(
                tool_call.function.name,
                tool_call.function.arguments,
            )

    Args:
        capabilities: Optional list of capability IDs to expose.  If ``None``,
                      all runtime capabilities are included.

    Returns:
        List of OpenAI tool definition dicts.
    """
    caps = _resolve_capabilities(capabilities)
    tools: list[dict[str, Any]] = []

    for cap_info in caps:
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": cap_info["id"].replace(".", "_"),
                    "description": cap_info.get("description", cap_info["id"]),
                    "parameters": _build_json_schema(cap_info),
                },
            }
        )

    return tools


def execute_openai_tool_call(
    function_name: str,
    function_args_json: str,
) -> str:
    """Execute an OpenAI function call and return the result as JSON string.

    Designed to be called when processing ``tool_calls`` from the Chat
    Completions API response.  OpenAI sends function arguments as a JSON
    string, which this helper parses automatically.

    Args:
        function_name: The function name (underscored).
        function_args_json: JSON string of function arguments.

    Returns:
        JSON string of the execution result (or error).

    Usage::

        result_json = execute_openai_tool_call(
            tool_call.function.name,
            tool_call.function.arguments,
        )
        # Send back as: {"role": "tool", "tool_call_id": tool_call.id, "content": result_json}
    """
    cap_id = function_name.replace("_", ".")
    try:
        args = (
            json.loads(function_args_json)
            if isinstance(function_args_json, str)
            else function_args_json
        )
    except json.JSONDecodeError as exc:
        return json.dumps(
            {"error": f"Invalid JSON arguments: {exc}", "code": "invalid_request"}
        )

    try:
        result = execute_capability(cap_id, args)
        return json.dumps(result, default=str)
    except Exception as exc:
        return json.dumps({"error": str(exc), "code": _classify_error(exc)})


def as_gemini_tools(
    capabilities: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Build Google Gemini-compatible tool definitions.

    Returns a list containing one tool dict with ``function_declarations``
    ready to pass as ``tools=`` to ``genai.GenerativeModel.generate_content()``.
    No Google SDK dependency required.

    Gemini uses UPPERCASE type names (``STRING``, ``INTEGER``, etc.) and
    wraps functions in a ``function_declarations`` array.

    The returned structure::

        [
            {
                "function_declarations": [
                    {
                        "name": "text_content_summarize",
                        "description": "...",
                        "parameters": { "type": "OBJECT", "properties": {...}, "required": [...] }
                    },
                    ...
                ]
            }
        ]

    Usage::

        from sdk.embedded import as_gemini_tools, execute_gemini_tool_call
        import google.generativeai as genai

        model = genai.GenerativeModel("gemini-pro")
        tools = as_gemini_tools()

        response = model.generate_content("Summarize this: ...", tools=tools)

        # Process function calls:
        for part in response.parts:
            if fn := part.function_call:
                result = execute_gemini_tool_call(fn.name, dict(fn.args))

    Args:
        capabilities: Optional list of capability IDs to expose.  If ``None``,
                      all runtime capabilities are included.

    Returns:
        List containing one dict with ``function_declarations``.
    """
    caps = _resolve_capabilities(capabilities)
    declarations: list[dict[str, Any]] = []

    for cap_info in caps:
        declarations.append(
            {
                "name": cap_info["id"].replace(".", "_"),
                "description": cap_info.get("description", cap_info["id"]),
                "parameters": _build_gemini_schema(cap_info),
            }
        )

    return [{"function_declarations": declarations}]


def execute_gemini_tool_call(
    function_name: str,
    function_args: dict[str, Any],
) -> str:
    """Execute a Gemini function call and return the result as JSON string.

    Designed to be called when processing ``function_call`` parts from the
    Gemini response.

    Args:
        function_name: The function name (underscored).
        function_args: Arguments dict from the function call.

    Returns:
        JSON string of the execution result (or error).

    Usage::

        result_json = execute_gemini_tool_call(fn.name, dict(fn.args))
        # Send back via genai.types.FunctionResponse(name=fn.name, response=json.loads(result_json))
    """
    cap_id = function_name.replace("_", ".")
    try:
        result = execute_capability(cap_id, function_args)
        return json.dumps(result, default=str)
    except Exception as exc:
        return json.dumps({"error": str(exc), "code": _classify_error(exc)})


def _classify_error(exc: Exception) -> str:
    """Map an exception to an error taxonomy code.

    Uses the canonical mapping from ``runtime.openapi_error_contract``
    when available, falls back to ``internal_error``.
    """
    try:
        from runtime.openapi_error_contract import map_runtime_error_to_http

        return map_runtime_error_to_http(exc).code
    except Exception:
        return "internal_error"


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

# JSON Schema type string → valid JSON Schema type keyword
_JSON_SCHEMA_TYPE_MAP: dict[str, str] = {
    "string": "string",
    "integer": "integer",
    "number": "number",
    "boolean": "boolean",
    "array": "array",
    "object": "object",
}

# Gemini uses UPPERCASE type names (google.genai REST / SDK convention)
_GEMINI_TYPE_MAP: dict[str, str] = {
    "string": "STRING",
    "integer": "INTEGER",
    "number": "NUMBER",
    "boolean": "BOOLEAN",
    "array": "ARRAY",
    "object": "OBJECT",
}


def _normalize_outputs_to_skill_contract(
    skill: Any, outputs: dict[str, Any]
) -> dict[str, Any]:
    """Normalize outputs to the skill contract for stable downstream composition.

    The runtime guarantees required outputs are present at execution time, but
    this helper makes the returned payload deterministic for consumers by:
    - keeping only declared output fields,
    - filling missing required fields with safe type defaults,
    - coercing values to the declared top-level field type.
    """
    if not getattr(skill, "outputs", None):
        return dict(outputs)

    normalized: dict[str, Any] = {}
    for name, spec in skill.outputs.items():
        has_value = name in outputs

        if has_value:
            value = outputs[name]
        elif spec.default is not None:
            value = spec.default
        elif spec.required:
            value = _default_value_for_field_type(spec.type)
        else:
            continue

        normalized[name] = _coerce_value_to_field_type(value, spec.type)

    return normalized


def _default_value_for_field_type(field_type: str) -> Any:
    t = (field_type or "").strip().lower()
    if t == "string":
        return ""
    if t == "integer":
        return 0
    if t == "number":
        return 0.0
    if t == "boolean":
        return False
    if t == "array":
        return []
    if t == "object":
        return {}
    return None


def _coerce_value_to_field_type(value: Any, field_type: str) -> Any:
    t = (field_type or "").strip().lower()

    if t == "string":
        return "" if value is None else str(value)

    if t == "integer":
        try:
            if isinstance(value, bool):
                return int(value)
            return int(value)
        except Exception:
            return 0

    if t == "number":
        try:
            if isinstance(value, bool):
                return float(int(value))
            return float(value)
        except Exception:
            return 0.0

    if t == "boolean":
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            v = value.strip().lower()
            if v in {"true", "1", "yes", "y", "on"}:
                return True
            if v in {"false", "0", "no", "n", "off", ""}:
                return False
        return bool(value)

    if t == "array":
        if isinstance(value, list):
            return value
        if isinstance(value, tuple):
            return list(value)
        if value is None:
            return []
        return [value]

    if t == "object":
        if isinstance(value, dict):
            return value
        return {}

    return value


def _build_json_schema(cap_info: dict[str, Any]) -> dict[str, Any]:
    """Build a JSON Schema ``object`` from a capability's inputs metadata.

    This is the **shared helper** used by the MCP server and the Anthropic /
    OpenAI native adapters.  It converts the ``inputs`` dict produced by
    :func:`list_capabilities` into a standard JSON Schema ``{type, properties,
    required}`` object.

    Handles all FieldSpec types including ``array`` (emits ``items: {}`` when
    the element type is unspecified) and ``object`` (emits without sub-properties
    when unspecified, which is valid JSON Schema).

    Args:
        cap_info: A capability dict as returned by :func:`list_capabilities`,
                  containing at least an ``"inputs"`` key.

    Returns:
        A JSON Schema ``object`` dict ready to embed as ``inputSchema`` (MCP),
        ``input_schema`` (Anthropic) or ``parameters`` (OpenAI).

    Example::

        >>> schema = _build_json_schema({"inputs": {"text": {"type": "string", "required": True}}})
        >>> schema["required"]
        ['text']
    """
    inputs_spec: dict[str, Any] = cap_info.get("inputs", {})
    properties: dict[str, Any] = {}
    required: list[str] = []

    for name, spec in inputs_spec.items():
        json_type = _JSON_SCHEMA_TYPE_MAP.get(spec.get("type", "string"), "string")
        prop: dict[str, Any] = {"type": json_type}

        desc = spec.get("description", "")
        if desc:
            prop["description"] = desc

        # array → always include items for strict-mode consumers (e.g. OpenAI)
        if json_type == "array":
            prop["items"] = {}

        properties[name] = prop

        if spec.get("required", False):
            required.append(name)

    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
    }
    if required:
        schema["required"] = sorted(required)
    return schema


def _build_gemini_schema(cap_info: dict[str, Any]) -> dict[str, Any]:
    """Build a Gemini-compatible parameter schema from a capability's inputs.

    Google Gemini (``google-generativeai`` SDK and REST API) uses UPPERCASE
    type names (``STRING``, ``INTEGER``, etc.) instead of the lowercase
    JSON Schema convention.  This helper mirrors :func:`_build_json_schema`
    but emits the Gemini format.

    Args:
        cap_info: A capability dict as returned by :func:`list_capabilities`.

    Returns:
        A Gemini-compatible schema dict with ``type``, ``properties``, and
        ``required`` using UPPERCASE type names.
    """
    inputs_spec: dict[str, Any] = cap_info.get("inputs", {})
    properties: dict[str, Any] = {}
    required: list[str] = []

    for name, spec in inputs_spec.items():
        gemini_type = _GEMINI_TYPE_MAP.get(spec.get("type", "string"), "STRING")
        prop: dict[str, Any] = {"type": gemini_type}

        desc = spec.get("description", "")
        if desc:
            prop["description"] = desc

        if gemini_type == "ARRAY":
            prop["items"] = {"type": "STRING"}

        properties[name] = prop

        if spec.get("required", False):
            required.append(name)

    schema: dict[str, Any] = {
        "type": "OBJECT",
        "properties": properties,
    }
    if required:
        schema["required"] = sorted(required)
    return schema


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

"""MCP Server that exposes all agent-skills capabilities as MCP tools.

This is a **real MCP server** implementing the Model Context Protocol over
JSON-RPC 2.0 with stdio transport (primary) and optional SSE transport.

Every capability registered in the runtime is dynamically discovered via
:func:`sdk.embedded.list_capabilities` and exposed as an MCP tool with:

- ``name``: the capability ID (e.g. ``text.content.summarize``)
- ``description``: from the CapabilitySpec
- ``inputSchema``: JSON Schema generated from the capability's inputs

Tool execution delegates to :func:`sdk.embedded.execute_capability` so all
bindings, services, and protocol routing of the runtime are honoured.

Usage (stdio transport — for Claude Desktop, Cursor, VS Code Copilot)::

    python -m official_mcp_servers

Or via the CLI::

    agent-skills mcp-serve

Configuration for Claude Desktop (``claude_desktop_config.json``)::

    {
      "mcpServers": {
        "agent-skills": {
          "command": "python",
          "args": ["-m", "official_mcp_servers"]
        }
      }
    }
"""

from __future__ import annotations

from concurrent.futures import (
    Future,
    ThreadPoolExecutor,
    TimeoutError as FutureTimeoutError,
)
import json
import logging
from threading import Lock
from typing import Any
import uuid

import anyio
from mcp.server import Server
from mcp.types import (
    TextContent,
    Tool,
)

logger = logging.getLogger(__name__)

_CONTRACT_INSPECT_TOOL = "contract.inspect"
_SKILL_INSPECT_TOOL = "skill.inspect"
_RUN_STATUS_TOOL = "run.status"
_SKILL_PREFIX = "skill."
_ASYNC_ARG = "_async"
_MAX_WAIT_MS_ARG = "_max_wait_ms"
_INCLUDE_DIAGNOSTICS_ARG = "_include_diagnostics"
_EXECUTION_MODE_ARG = "_execution_mode"
_EXECUTION_MODE_SYNC_ONLY = "sync_only"
_EXECUTION_MODE_ASYNC_ALLOWED = "async_allowed"
_DEFAULT_SKILL_WAIT_MS = 55000

_RUN_EXECUTOR = ThreadPoolExecutor(max_workers=8, thread_name_prefix="mcp-tool")
_RUNS_LOCK = Lock()
_RUN_FUTURES: dict[str, Future[Any]] = {}
_RUN_TOOL_NAME: dict[str, str] = {}
_PLAN_CACHE_LOCK = Lock()
_LAST_COMPILED_PLAN: dict[str, Any] | None = None

# Define global timeout and polling interval
DEFAULT_TIMEOUT_MS = 30000  # 30 seconds
default_polling_interval = 1.0  # 1 second

# ---------------------------------------------------------------------------
# Server instance
# ---------------------------------------------------------------------------

server = Server("agent-skills")
"""The singleton MCP server instance.

Handlers are registered via the ``@server.list_tools()`` and
``@server.call_tool()`` decorators below.
"""


# ---------------------------------------------------------------------------
# Capability discovery (lazy, cached)
# ---------------------------------------------------------------------------

_capabilities_cache: list[dict[str, Any]] | None = None


def _get_capabilities() -> list[dict[str, Any]]:
    """Return the cached list of runtime capabilities.

    The list is fetched once from :func:`sdk.embedded.list_capabilities` and
    cached for the lifetime of the server process.  This avoids repeated
    filesystem scans on every ``tools/list`` request while ensuring the full
    capability catalog is available from startup.
    """
    global _capabilities_cache
    if _capabilities_cache is None:
        from sdk.embedded import list_capabilities

        _capabilities_cache = list_capabilities()
        logger.info(
            "Discovered %d capabilities for MCP exposure.", len(_capabilities_cache)
        )
    return _capabilities_cache


def reset_cache() -> None:
    """Clear the capability cache (useful for testing)."""
    global _capabilities_cache
    _capabilities_cache = None


# ---------------------------------------------------------------------------
# Skill discovery (lazy, cached)
# ---------------------------------------------------------------------------

_skills_cache: list[dict[str, Any]] | None = None


def _get_skills() -> list[dict[str, Any]]:
    """Return the cached list of available skills."""
    global _skills_cache
    if _skills_cache is None:
        from sdk.embedded import list_skills

        _skills_cache = list_skills()
        logger.info("Discovered %d skills for MCP exposure.", len(_skills_cache))
    return _skills_cache


def reset_skills_cache() -> None:
    """Clear the skill cache (useful for testing)."""
    global _skills_cache
    _skills_cache = None


def _build_skill_inspect_result(
    skill_id: str,
    skills: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return metadata for a skill id."""
    target = next((s for s in skills if s.get("id") == skill_id), None)
    if target is None:
        raise ValueError(f"Skill '{skill_id}' is not available in this MCP session.")
    return {
        "id": target.get("id"),
        "name": target.get("name") or "",
        "description": target.get("description") or "",
        "inputs": target.get("inputs") or {},
        "outputs": target.get("outputs") or {},
    }


def _build_skill_input_schema(skill: dict[str, Any]) -> dict[str, Any]:
    """Build a minimal JSON Schema for a skill's inputs."""
    inputs = skill.get("inputs") or {}
    properties: dict[str, Any] = {}
    required: list[str] = []
    allowed_types = {"string", "number", "integer", "boolean", "object", "array"}
    for field_name, field_spec in inputs.items():
        if not isinstance(field_spec, dict):
            field_spec = {}
        ftype = field_spec.get("type", "string")
        if not isinstance(ftype, str) or ftype not in allowed_types:
            ftype = "string"

        prop: dict[str, Any] = {"type": ftype}
        if ftype == "array":
            # OpenAI tool schemas require "items" for array-typed fields.
            prop["items"] = {}
        elif ftype == "object":
            # Keep object inputs permissive unless richer nested schema exists.
            prop["additionalProperties"] = True

        desc = field_spec.get("description", "")
        if desc:
            prop["description"] = desc
        properties[field_name] = prop
        if field_spec.get("required", False):
            required.append(field_name)
    schema: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema


def _build_contract_inspect_result(
    capability_id: str,
    caps: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return canonical contract details for a capability id."""
    target = next((c for c in caps if c.get("id") == capability_id), None)
    if target is None:
        raise ValueError(
            f"Capability '{capability_id}' is not available in this MCP session."
        )

    inputs = target.get("inputs") if isinstance(target.get("inputs"), dict) else {}
    outputs = target.get("outputs") if isinstance(target.get("outputs"), dict) else {}
    required_inputs = sorted(
        [
            name
            for name, spec in inputs.items()
            if isinstance(spec, dict) and spec.get("required", False)
        ]
    )

    return {
        "id": target.get("id"),
        "description": target.get("description") or "",
        "inputs": inputs,
        "required_inputs": required_inputs,
        "outputs": outputs,
    }


def _with_async_controls(schema: dict[str, Any]) -> dict[str, Any]:
    """Add optional async controls to an input schema."""
    out = dict(schema) if isinstance(schema, dict) else {"type": "object"}
    props = out.get("properties")
    if not isinstance(props, dict):
        props = {}
    props[_ASYNC_ARG] = {
        "type": "boolean",
        "description": (
            "If true, returns immediately with run_id and executes in background. "
            "Use run.status to poll for completion."
        ),
    }
    props[_MAX_WAIT_MS_ARG] = {
        "type": "integer",
        "description": (
            "Optional max wait in milliseconds before returning a running status "
            "with run_id."
        ),
        "minimum": 1000,
        "maximum": 120000,
    }
    props[_INCLUDE_DIAGNOSTICS_ARG] = {
        "type": "boolean",
        "description": (
            "If true, include binding resolution and fallback diagnostics "
            "in the result (skill tools only)."
        ),
    }
    props[_EXECUTION_MODE_ARG] = {
        "type": "string",
        "enum": [_EXECUTION_MODE_SYNC_ONLY, _EXECUTION_MODE_ASYNC_ALLOWED],
        "description": (
            "Execution behavior when sync wait window is exceeded. "
            "sync_only: never return run_id placeholders; async_allowed: allow background run_id fallback."
        ),
    }
    out["properties"] = props
    return out


def _default_value_for_type(field_type: str) -> Any:
    t = (field_type or "").strip().lower()
    if t == "string":
        return ""
    if t == "number":
        return 0.0
    if t == "integer":
        return 0
    if t == "boolean":
        return False
    if t == "array":
        return []
    if t == "object":
        return {}
    return None


def _build_running_skill_placeholder(
    skill_id: str,
    run_id: str,
    message: str,
    skills: list[dict[str, Any]],
) -> dict[str, Any]:
    target = next((s for s in skills if s.get("id") == skill_id), None)
    outputs = target.get("outputs", {}) if isinstance(target, dict) else {}
    payload: dict[str, Any] = {}
    if isinstance(outputs, dict):
        for name, spec in outputs.items():
            ftype = spec.get("type", "object") if isinstance(spec, dict) else "object"
            payload[name] = _default_value_for_type(ftype)
    if "report_status" in payload:
        payload["report_status"] = "running"
    payload["_run"] = {
        "status": "running",
        "run_id": run_id,
        "retryable": True,
        "message": message,
    }
    return payload


def _build_sync_timeout_skill_fallback(
    skill_id: str,
    message: str,
    skills: list[dict[str, Any]],
) -> dict[str, Any]:
    target = next((s for s in skills if s.get("id") == skill_id), None)
    outputs = target.get("outputs", {}) if isinstance(target, dict) else {}
    payload: dict[str, Any] = {}
    if isinstance(outputs, dict):
        for name, spec in outputs.items():
            ftype = spec.get("type", "object") if isinstance(spec, dict) else "object"
            payload[name] = _default_value_for_type(ftype)
    payload["meta"] = {
        "fallback_used": True,
        "fallback_steps_count": 0,
        "step_diagnostics": [],
        "limitation": message,
    }
    return payload


def _extract_execution_controls(args: dict[str, Any]) -> tuple[bool, int | None]:
    async_requested = bool(args.pop(_ASYNC_ARG, False))
    raw_wait = args.pop(_MAX_WAIT_MS_ARG, None)
    wait_ms: int | None = None
    if raw_wait is not None:
        try:
            wait_ms = int(raw_wait)
        except Exception:
            wait_ms = None
    if wait_ms is not None:
        wait_ms = max(1000, min(wait_ms, 180000))
    return async_requested, wait_ms


def _extract_execution_mode(args: dict[str, Any]) -> str:
    raw_mode = args.pop(_EXECUTION_MODE_ARG, _EXECUTION_MODE_ASYNC_ALLOWED)
    if not isinstance(raw_mode, str):
        return _EXECUTION_MODE_ASYNC_ALLOWED
    normalized = raw_mode.strip().lower()
    if normalized in {_EXECUTION_MODE_SYNC_ONLY, _EXECUTION_MODE_ASYNC_ALLOWED}:
        return normalized
    return _EXECUTION_MODE_ASYNC_ALLOWED


def _extract_include_diagnostics(args: dict[str, Any]) -> bool:
    return bool(args.pop(_INCLUDE_DIAGNOSTICS_ARG, True))  # Default to True


def _extract_compiled_plan_candidate(planner_output: str) -> Any:
    """Best-effort extraction of compiled plan payload from planner text."""
    import json
    import re

    text = planner_output.strip()
    if not text:
        return None

    # Fast path: planner output is already JSON object.
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            if "compiled_plan" in parsed:
                return parsed.get("compiled_plan")
            if "compiled_plan_json" in parsed:
                return parsed.get("compiled_plan_json")
    except Exception:
        pass

    # Fallback for text blobs containing compiled_plan_json as an embedded string.
    match = re.search(
        r'"compiled_plan_json"\s*:\s*"(?P<cp>\{.*?\})"\s*(?:,\s*"|\}$)',
        text,
        flags=re.DOTALL,
    )
    if match:
        cp_raw = match.group("cp")
        try:
            return bytes(cp_raw, "utf-8").decode("unicode_escape")
        except Exception:
            return cp_raw

    # Fallback for text blobs containing compiled_plan object directly.
    match_obj = re.search(
        r'"compiled_plan"\s*:\s*(?P<cp>\{.*\})\s*(?:,\s*"|\}$)',
        text,
        flags=re.DOTALL,
    )
    if match_obj:
        cp_raw = match_obj.group("cp")
        try:
            return json.loads(cp_raw)
        except Exception:
            return cp_raw

    return None


def _normalize_execute_from_plan_args(
    name: str, args: dict[str, Any]
) -> dict[str, Any]:
    """Accept aliases used by external planners for execute-from-plan."""
    if name != f"{_SKILL_PREFIX}agent.execute-from-plan":
        return args

    normalized = dict(args)

    if normalized.get("compiled_plan") is None:
        cp_json = normalized.get("compiled_plan_json")
        if isinstance(cp_json, str) and cp_json.strip():
            normalized["compiled_plan"] = cp_json

    if normalized.get("compiled_plan") is None:
        planner_output = normalized.get("planner_output")
        if isinstance(planner_output, str) and planner_output.strip():
            extracted = _extract_compiled_plan_candidate(planner_output)
            if extracted is not None:
                normalized["compiled_plan"] = extracted

    if normalized.get("compiled_plan") is None:
        # Last-resort fallback: reuse latest planner artifact seen by this MCP.
        with _PLAN_CACHE_LOCK:
            cached_plan = _LAST_COMPILED_PLAN
        if isinstance(cached_plan, dict):
            normalized["compiled_plan"] = cached_plan

    # Ensure compiled_plan is an object even when provided as JSON string.
    compiled_plan = normalized.get("compiled_plan")
    if isinstance(compiled_plan, str):
        import json

        cp_text = compiled_plan.strip()
        if cp_text:
            try:
                parsed = json.loads(cp_text)
                if isinstance(parsed, dict):
                    normalized["compiled_plan"] = parsed
            except Exception:
                # Handle planner payloads that are escaped one extra time.
                try:
                    unescaped = bytes(cp_text, "utf-8").decode("unicode_escape")
                    parsed = json.loads(unescaped)
                    if isinstance(parsed, dict):
                        normalized["compiled_plan"] = parsed
                except Exception:
                    pass

    return normalized


def _extract_compiled_plan_from_result(result: Any) -> dict[str, Any] | None:
    """Extract compiled_plan object from planner result payload."""
    import json

    if not isinstance(result, dict):
        return None

    plan_obj = result.get("compiled_plan")
    if isinstance(plan_obj, dict):
        return plan_obj

    plan_json = result.get("compiled_plan_json")
    if isinstance(plan_json, str) and plan_json.strip():
        try:
            parsed = json.loads(plan_json)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            try:
                unescaped = bytes(plan_json.strip(), "utf-8").decode("unicode_escape")
                parsed = json.loads(unescaped)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                return None
    return None


def _maybe_cache_planner_result(name: str, result: Any) -> None:
    """Cache planner compiled plan for executor fallback within same MCP session."""
    if name != f"{_SKILL_PREFIX}agent.orchestrate-from-prompt":
        return

    plan = _extract_compiled_plan_from_result(result)
    if isinstance(plan, dict):
        with _PLAN_CACHE_LOCK:
            global _LAST_COMPILED_PLAN
            _LAST_COMPILED_PLAN = plan


def _execute_runtime_tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
    from sdk.embedded import execute_capability, execute, execute_with_meta

    if name.startswith(_SKILL_PREFIX):
        include_diagnostics = _extract_include_diagnostics(args)
        if include_diagnostics:
            return execute_with_meta(name[len(_SKILL_PREFIX) :], args)
        return execute(name[len(_SKILL_PREFIX) :], args)
    return execute_capability(name, args)


def _start_background_run(name: str, args: dict[str, Any]) -> str:
    run_id = uuid.uuid4().hex
    future = _RUN_EXECUTOR.submit(_execute_runtime_tool, name, dict(args))
    with _RUNS_LOCK:
        _RUN_FUTURES[run_id] = future
        _RUN_TOOL_NAME[run_id] = name
    return run_id


def _wait_for_run_result(
    run_id: str, timeout_ms: int = DEFAULT_TIMEOUT_MS
) -> tuple[bool, dict[str, Any]]:
    with _RUNS_LOCK:
        fut = _RUN_FUTURES.get(run_id)
        tool_name = _RUN_TOOL_NAME.get(run_id, "")
    if fut is None:
        raise ValueError(f"Unknown run_id '{run_id}'.")
    try:
        result = fut.result(timeout=timeout_ms / 1000.0)
        return True, {
            "status": "completed",
            "run_id": run_id,
            "tool": tool_name,
            "result": result,
        }
    except FutureTimeoutError:
        return False, {"status": "running", "run_id": run_id, "tool": tool_name}


def _get_run_status_payload(run_id: str) -> dict[str, Any]:
    with _RUNS_LOCK:
        fut = _RUN_FUTURES.get(run_id)
        tool_name = _RUN_TOOL_NAME.get(run_id, "")
    if fut is None:
        raise ValueError(f"Unknown run_id '{run_id}'.")
    if not fut.done():
        return {"status": "running", "run_id": run_id, "tool": tool_name}
    try:
        result = fut.result()
        return {
            "status": "completed",
            "run_id": run_id,
            "tool": tool_name,
            "result": result,
        }
    except Exception as exc:
        return {
            "status": "error",
            "run_id": run_id,
            "tool": tool_name,
            "error": str(exc),
            "code": _classify_error(exc),
        }


# ---------------------------------------------------------------------------
# MCP handlers
# ---------------------------------------------------------------------------


@server.list_tools()
async def list_tools() -> list[Tool]:
    """Dynamically list all runtime capabilities and skills as MCP tools.

    Each capability's inputs are converted to a JSON Schema via the shared
    :func:`sdk.embedded._build_json_schema` helper so that MCP clients can
    present proper parameter forms and validate user input.

    Skills are exposed with the ``skill:`` prefix (e.g. ``skill:my.skill.id``)
    so they are visually distinct from atomic capabilities and can be dispatched
    directly as pre-built multi-step flows.
    """
    from sdk.embedded import _build_json_schema

    caps = _get_capabilities()
    skills = _get_skills()

    tools: list[Tool] = [
        Tool(
            name=_CONTRACT_INSPECT_TOOL,
            description=(
                "Return canonical contract details for a capability id, including "
                "required inputs and full input/output schemas."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "capability_id": {
                        "type": "string",
                        "description": "Exact capability id to inspect, e.g. model.output.generate",
                    }
                },
                "required": ["capability_id"],
            },
        ),
        Tool(
            name=_SKILL_INSPECT_TOOL,
            description=(
                "Return metadata for a skill id, including name, description and IO schema. "
                "Use this to confirm inputs before executing a skill."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "skill_id": {
                        "type": "string",
                        "description": "Exact skill id to inspect, e.g. experiment.structured-decision",
                    }
                },
                "required": ["skill_id"],
            },
        ),
        Tool(
            name=_RUN_STATUS_TOOL,
            description=(
                "Return status for a background run_id created by _async or _max_wait_ms execution controls."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "run_id": {
                        "type": "string",
                        "description": "Run id returned by a previous tool call.",
                    }
                },
                "required": ["run_id"],
            },
        ),
    ]

    for cap_info in caps:
        desc = cap_info.get("description") or ""
        input_names = list((cap_info.get("inputs") or {}).keys())
        if input_names and not desc:
            desc = f"Capability {cap_info['id']}. Inputs: {', '.join(input_names)}."
        elif not desc:
            desc = f"Execute capability {cap_info['id']}."
        tools.append(
            Tool(
                name=cap_info["id"],
                description=desc,
                inputSchema=_with_async_controls(_build_json_schema(cap_info)),
            )
        )

    for skill_info in skills:
        sid = skill_info.get("id", "")
        if not sid:
            continue
        desc = skill_info.get("description") or f"Execute skill {sid}."
        desc = f"[SKILL] {desc}"
        tools.append(
            Tool(
                name=f"{_SKILL_PREFIX}{sid}",
                description=desc,
                inputSchema=_with_async_controls(_build_skill_input_schema(skill_info)),
            )
        )

    return tools


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any] | None) -> list[TextContent]:
    """Execute a capability or skill via the embedded runtime and return the result.

    Capabilities are dispatched directly by id.
    Skills are dispatched when the tool name starts with ``skill.`` prefix.
    ``contract.inspect`` and ``skill.inspect`` return metadata without execution.
    """
    caps = _get_capabilities()
    skills = _get_skills()
    known_ids = {c["id"] for c in caps}
    known_ids.add(_CONTRACT_INSPECT_TOOL)
    known_ids.add(_SKILL_INSPECT_TOOL)
    known_ids.add(_RUN_STATUS_TOOL)
    for s in skills:
        if s.get("id"):
            known_ids.add(f"{_SKILL_PREFIX}{s['id']}")

    if name not in known_ids:
        raise ValueError(
            f"Unknown tool '{name}'. Use tools/list to see available tools."
        )

    safe_args = dict(arguments) if isinstance(arguments, dict) else {}
    safe_args = _normalize_execute_from_plan_args(name, safe_args)

    execution_mode = _extract_execution_mode(safe_args)

    try:
        if name == _CONTRACT_INSPECT_TOOL:
            capability_id = safe_args.get("capability_id")
            if not isinstance(capability_id, str) or not capability_id:
                raise ValueError(
                    "contract.inspect requires non-empty string argument 'capability_id'."
                )
            result = _build_contract_inspect_result(capability_id, caps)

        elif name == _SKILL_INSPECT_TOOL:
            skill_id = safe_args.get("skill_id")
            if not isinstance(skill_id, str) or not skill_id:
                raise ValueError(
                    "skill.inspect requires non-empty string argument 'skill_id'."
                )
            # Accept both prefixed ("skill.research.generate-briefing") and
            # bare ("research.generate-briefing") skill ids so the Planner can
            # pass the tool name directly from its tools list.
            if skill_id.startswith(_SKILL_PREFIX):
                skill_id = skill_id[len(_SKILL_PREFIX) :]
            result = _build_skill_inspect_result(skill_id, skills)

        elif name == _RUN_STATUS_TOOL:
            run_id = safe_args.get("run_id")
            if not isinstance(run_id, str) or not run_id:
                raise ValueError(
                    "run.status requires non-empty string argument 'run_id'."
                )
            result = _get_run_status_payload(run_id)

        elif name.startswith(_SKILL_PREFIX):
            skill_id = name[len(_SKILL_PREFIX) :]
            async_requested, wait_ms = _extract_execution_controls(safe_args)
            if async_requested and execution_mode == _EXECUTION_MODE_SYNC_ONLY:
                raise ValueError(
                    "_async=true is not allowed when _execution_mode='sync_only'."
                )
            # For execute-from-plan: if plan is missing, force async to get it from cache later.
            # If plan exists, allow sync execution with extended timeout.
            if skill_id == "agent.execute-from-plan":
                has_plan = bool(
                    safe_args.get("compiled_plan")
                    or safe_args.get("compiled_plan_json")
                    or safe_args.get("planner_output")
                )
                if not has_plan and not async_requested:
                    # No plan provided and not explicitly async → try cached plan later
                    async_requested = True
            effective_wait_ms = (
                wait_ms if wait_ms is not None else _DEFAULT_SKILL_WAIT_MS
            )
            if async_requested:
                run_id = _start_background_run(name, safe_args)
                result = _build_running_skill_placeholder(
                    skill_id,
                    run_id,
                    "Execution started in background. Poll run.status with this run_id.",
                    skills,
                )
            elif effective_wait_ms > 0:
                run_id = _start_background_run(name, safe_args)
                done, payload = await anyio.to_thread.run_sync(
                    _wait_for_run_result,
                    run_id,
                    effective_wait_ms,
                )
                if done:
                    result = payload["result"]
                    _maybe_cache_planner_result(name, result)
                else:
                    if execution_mode == _EXECUTION_MODE_SYNC_ONLY:
                        result = _build_sync_timeout_skill_fallback(
                            skill_id,
                            (
                                "Execution exceeded max wait window in sync_only mode; "
                                "no background run id was returned."
                            ),
                            skills,
                        )
                    else:
                        result = _build_running_skill_placeholder(
                            skill_id,
                            run_id,
                            (
                                "Execution exceeded max wait window. "
                                "Poll run.status with this run_id for completion."
                            ),
                            skills,
                        )
            else:
                result = _execute_runtime_tool(name, safe_args)
                _maybe_cache_planner_result(name, result)

        else:
            async_requested, wait_ms = _extract_execution_controls(safe_args)
            if async_requested and execution_mode == _EXECUTION_MODE_SYNC_ONLY:
                raise ValueError(
                    "_async=true is not allowed when _execution_mode='sync_only'."
                )
            if async_requested:
                run_id = _start_background_run(name, safe_args)
                result = {
                    "status": "running",
                    "run_id": run_id,
                    "tool": name,
                    "retryable": True,
                    "message": "Execution started in background. Poll run.status with this run_id.",
                }
            elif wait_ms is not None and wait_ms > 0:
                run_id = _start_background_run(name, safe_args)
                done, payload = await anyio.to_thread.run_sync(
                    _wait_for_run_result,
                    run_id,
                    wait_ms,
                )
                if done:
                    result = payload["result"]
                else:
                    if execution_mode == _EXECUTION_MODE_SYNC_ONLY:
                        result = {
                            "error": (
                                "Execution exceeded max wait window in sync_only mode; "
                                "no background run id was returned."
                            ),
                            "code": "sync_window_exceeded",
                            "tool": name,
                            "retryable": False,
                        }
                    else:
                        result = {
                            "status": "running",
                            "run_id": run_id,
                            "tool": name,
                            "retryable": True,
                            "message": (
                                "Execution exceeded max wait window. "
                                "Poll run.status with this run_id for completion."
                            ),
                        }
            else:
                result = _execute_runtime_tool(name, safe_args)
            _maybe_cache_planner_result(name, result)

    except Exception as exc:
        logger.error("Tool '%s' execution failed: %s", name, exc)
        code = _classify_error(exc)
        return [
            TextContent(
                type="text",
                text=json.dumps(
                    {
                        "error": str(exc),
                        "code": code,
                        "tool": name,
                    }
                ),
            )
        ]

    return [TextContent(type="text", text=json.dumps(result, default=str))]


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
# Entry point helpers
# ---------------------------------------------------------------------------


async def run_stdio() -> None:
    """Run the MCP server with stdio transport (JSON-RPC over stdin/stdout).

    This is the standard transport for MCP integrations with Claude Desktop,
    Cursor, VS Code Copilot, and other MCP clients.
    """
    from mcp.server.stdio import stdio_server

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


async def run_sse(host: str = "0.0.0.0", port: int = 8765) -> None:
    """Run the MCP server with SSE transport over HTTP.

    This transport is useful for browser-based or remote MCP clients.
    Requires ``uvicorn`` (installed with the ``asgi`` extra).

    Args:
        host: Bind address (default ``0.0.0.0``).
        port: Listen port (default ``8765``).
    """
    try:
        from mcp.server.sse import SseServerTransport
        from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
        import uvicorn
        from starlette.applications import Starlette
        from starlette.routing import Mount, Route
        from contextlib import asynccontextmanager
    except ImportError as exc:
        raise ImportError(
            "SSE transport requires additional dependencies. "
            "Install with: pip install 'orca-agent-skills[mcp,asgi]'"
        ) from exc

    sse = SseServerTransport("/messages/")
    session_manager = StreamableHTTPSessionManager(
        app=server,
        json_response=False,
        stateless=True,
    )

    async def handle_sse(request):
        async with sse.connect_sse(
            request.scope, request.receive, request._send
        ) as streams:
            await server.run(
                streams[0],
                streams[1],
                server.create_initialization_options(),
            )

    async def handle_mcp_asgi(scope, receive, send):
        await session_manager.handle_request(scope, receive, send)

    async def handle_root(request):
        from starlette.responses import JSONResponse

        return JSONResponse(
            {
                "message": "agent-skills MCP server",
                "endpoints": {
                    "/sse": "Server-Sent Events transport",
                    "/messages/": "SSE message handling",
                    "/mcp": "JSON-RPC over HTTP",
                },
            }
        )

    @asynccontextmanager
    async def lifespan(app):
        async with session_manager.run():
            yield

    app = Starlette(
        lifespan=lifespan,
        routes=[
            Route("/", endpoint=handle_root),
            Route("/sse", endpoint=handle_sse),
            Mount("/messages/", app=sse.handle_post_message),
            Mount("/mcp", app=handle_mcp_asgi),
        ],
    )

    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    srv = uvicorn.Server(config)
    await srv.serve()


def main(transport: str = "stdio", host: str = "0.0.0.0", port: int = 8765) -> None:
    """Launch the MCP server with the specified transport.

    This is the main entry point called by ``__main__.py`` and the CLI
    ``mcp-serve`` subcommand.

    Args:
        transport: ``"stdio"`` (default) or ``"sse"``.
        host: Bind address for SSE transport.
        port: Listen port for SSE transport.
    """
    import asyncio

    if transport == "sse":
        asyncio.run(run_sse(host=host, port=port))
    else:
        asyncio.run(run_stdio())

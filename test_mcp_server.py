"""Tests for the MCP server (official_mcp_servers/server.py).

Validates that the server correctly discovers capabilities, generates MCP tools,
executes capabilities via call_tool, and handles errors gracefully.

Uses unittest.mock to avoid requiring the full runtime stack.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

# ────────────────────────────────────────────────────────────────
# Fixtures
# ────────────────────────────────────────────────────────────────

_MOCK_CAPABILITIES = [
    {
        "id": "text.content.summarize",
        "description": "Produce a condensed version of text preserving key ideas.",
        "inputs": {
            "text": {
                "type": "string",
                "required": True,
                "description": "The input text.",
            },
            "max_length": {
                "type": "integer",
                "required": False,
                "description": "Maximum summary length.",
            },
        },
        "outputs": {
            "summary": {"type": "string"},
        },
    },
    {
        "id": "data.schema.validate",
        "description": "Validate structured data against a schema.",
        "inputs": {
            "data": {
                "type": "object",
                "required": True,
                "description": "Structured data.",
            },
            "schema": {
                "type": "object",
                "required": True,
                "description": "Validation schema.",
            },
        },
        "outputs": {
            "valid": {"type": "boolean"},
            "errors": {"type": "array"},
        },
    },
    {
        "id": "fs.file.read",
        "description": "Read content from a filesystem path.",
        "inputs": {
            "path": {"type": "string", "required": True, "description": "File path."},
        },
        "outputs": {
            "content": {"type": "string"},
        },
    },
]


_MOCK_SKILLS = [
    {
        "id": "decision.make",
        "name": "Make Decision",
        "description": "Structured decision workflow with recommendation and confidence.",
        "inputs": {
            "goal": {
                "type": "string",
                "required": True,
                "description": "Decision goal.",
            },
            "context_items": {
                "type": "array",
                "required": False,
                "description": "Supporting context items.",
            },
        },
        "outputs": {
            "recommendation": {"type": "string"},
            "confidence_level": {"type": "string"},
            "human_readable": {"type": "string"},
            "outputs_summary": {"type": "object"},
        },
    },
    {
        "id": "experiment.structured-decision",
        "name": "Structured Decision",
        "description": "Runs a structured decision flow with weighted criteria.",
        "inputs": {
            "topic": {
                "type": "string",
                "required": True,
                "description": "Decision topic.",
            },
            "options": {
                "type": "array",
                "required": True,
                "description": "List of options.",
            },
        },
        "outputs": {
            "decision": {"type": "string"},
            "rationale": {"type": "string"},
        },
    },
    {
        "id": "research.question.answer",
        "name": "Research Question Answer",
        "description": "Answers a research question with cited sources.",
        "inputs": {
            "question": {
                "type": "string",
                "required": True,
                "description": "The research question.",
            },
        },
        "outputs": {
            "answer": {"type": "string"},
            "sources": {"type": "array"},
        },
    },
]


@pytest.fixture(autouse=True)
def _reset_cache():
    """Reset the server's capability and skill caches before each test."""
    from official_mcp_servers.server import reset_cache, reset_skills_cache

    reset_cache()
    reset_skills_cache()
    yield
    reset_cache()
    reset_skills_cache()


# ────────────────────────────────────────────────────────────────
# list_tools tests
# ────────────────────────────────────────────────────────────────


class TestListTools:
    """Tests for the list_tools MCP handler."""

    @pytest.mark.asyncio
    async def test_lists_all_capabilities(self):
        """Server should list all capabilities and skills from the runtime as MCP tools."""
        with (
            patch("sdk.embedded.list_capabilities", return_value=_MOCK_CAPABILITIES),
            patch("sdk.embedded.list_skills", return_value=_MOCK_SKILLS),
        ):
            from official_mcp_servers.server import list_tools

            tools = await list_tools()

        # 3 meta-tools (contract.inspect, skill.inspect, run.status) + 3 capabilities + 3 skills
        assert len(tools) == 9
        names = {t.name for t in tools}
        assert "contract.inspect" in names
        assert "skill.inspect" in names
        assert "run.status" in names
        assert "text.content.summarize" in names
        assert "data.schema.validate" in names
        assert "fs.file.read" in names
        assert "skill.decision.make" in names
        assert "skill.experiment.structured-decision" in names
        assert "skill.research.question.answer" in names

    @pytest.mark.asyncio
    async def test_tool_has_description(self):
        with (
            patch("sdk.embedded.list_capabilities", return_value=_MOCK_CAPABILITIES),
            patch("sdk.embedded.list_skills", return_value=_MOCK_SKILLS),
        ):
            from official_mcp_servers.server import list_tools

            tools = await list_tools()

        summarize = [t for t in tools if t.name == "text.content.summarize"][0]
        assert "condensed" in summarize.description.lower()

    @pytest.mark.asyncio
    async def test_tool_has_input_schema(self):
        with (
            patch("sdk.embedded.list_capabilities", return_value=_MOCK_CAPABILITIES),
            patch("sdk.embedded.list_skills", return_value=_MOCK_SKILLS),
        ):
            from official_mcp_servers.server import list_tools

            tools = await list_tools()

        summarize = [t for t in tools if t.name == "text.content.summarize"][0]
        schema = summarize.inputSchema
        assert schema["type"] == "object"
        assert "text" in schema["properties"]
        assert schema["required"] == ["text"]

    @pytest.mark.asyncio
    async def test_empty_capabilities_returns_only_meta_tools(self):
        with (
            patch("sdk.embedded.list_capabilities", return_value=[]),
            patch("sdk.embedded.list_skills", return_value=[]),
        ):
            from official_mcp_servers.server import list_tools

            tools = await list_tools()

        assert len(tools) == 3
        names = {t.name for t in tools}
        assert "contract.inspect" in names
        assert "skill.inspect" in names
        assert "run.status" in names


# ────────────────────────────────────────────────────────────────
# call_tool tests
# ────────────────────────────────────────────────────────────────


class TestCallTool:
    """Tests for the call_tool MCP handler."""

    @pytest.mark.asyncio
    async def test_executes_capability(self):
        mock_result = {"summary": "Short version."}
        with (
            patch("sdk.embedded.list_capabilities", return_value=_MOCK_CAPABILITIES),
            patch("sdk.embedded.list_skills", return_value=_MOCK_SKILLS),
            patch(
                "sdk.embedded.execute_capability", return_value=mock_result
            ) as mock_exec,
        ):
            from official_mcp_servers.server import call_tool

            result = await call_tool(
                "text.content.summarize", {"text": "Hello world", "max_length": 20}
            )

        assert len(result) == 1
        parsed = json.loads(result[0].text)
        assert parsed["summary"] == "Short version."
        mock_exec.assert_called_once_with(
            "text.content.summarize", {"text": "Hello world", "max_length": 20}
        )

    @pytest.mark.asyncio
    async def test_decision_make_sync_success(self):
        mock_result = {
            "recommendation": "Proceed with option A.",
            "confidence_level": "medium",
            "human_readable": "Option A balances risk and speed.",
            "outputs_summary": {
                "recommendation": "Proceed with option A.",
                "confidence_score": 0.62,
                "confidence_level": "medium",
                "decision_quality_score": 72.0,
                "decision_quality_level": "good",
            },
            "meta": {
                "fallback_used": False,
                "fallback_steps_count": 0,
                "step_diagnostics": [],
            },
        }
        with (
            patch("sdk.embedded.list_capabilities", return_value=_MOCK_CAPABILITIES),
            patch("sdk.embedded.list_skills", return_value=_MOCK_SKILLS),
            patch("sdk.embedded.execute", return_value=mock_result) as mock_exec,
        ):
            from official_mcp_servers.server import call_tool

            result = await call_tool(
                "skill.decision.make",
                {"goal": "Choose infra approach", "context_items": []},
            )

        parsed = json.loads(result[0].text)
        assert parsed["recommendation"] == "Proceed with option A."
        assert parsed["confidence_level"] == "medium"
        assert parsed["meta"]["fallback_used"] is False
        mock_exec.assert_called_once_with(
            "decision.make", {"goal": "Choose infra approach", "context_items": []}
        )

    @pytest.mark.asyncio
    async def test_decision_make_sync_timeout_returns_controlled_fallback(self):
        with (
            patch("sdk.embedded.list_capabilities", return_value=_MOCK_CAPABILITIES),
            patch("sdk.embedded.list_skills", return_value=_MOCK_SKILLS),
            patch(
                "official_mcp_servers.server._start_background_run",
                return_value="run-1",
            ),
            patch(
                "official_mcp_servers.server._wait_for_run_result",
                return_value=(
                    False,
                    {
                        "status": "running",
                        "run_id": "run-1",
                        "tool": "skill.decision.make",
                    },
                ),
            ),
        ):
            from official_mcp_servers.server import call_tool

            result = await call_tool(
                "skill.decision.make",
                {
                    "goal": "Choose infra approach",
                    "_max_wait_ms": 1000,
                    "_execution_mode": "sync_only",
                },
            )

        parsed = json.loads(result[0].text)
        assert parsed["recommendation"] == ""
        assert parsed["confidence_level"] == ""
        assert isinstance(parsed["outputs_summary"], dict)
        assert parsed["meta"]["fallback_used"] is True
        assert parsed["meta"]["fallback_steps_count"] == 0
        assert isinstance(parsed["meta"]["step_diagnostics"], list)
        assert "limitation" in parsed["meta"]
        assert "run_id" not in json.dumps(parsed)

    @pytest.mark.asyncio
    async def test_skill_async_start_and_poll_status(self):
        with (
            patch("sdk.embedded.list_capabilities", return_value=_MOCK_CAPABILITIES),
            patch("sdk.embedded.list_skills", return_value=_MOCK_SKILLS),
            patch(
                "official_mcp_servers.server._start_background_run",
                return_value="run-42",
            ),
            patch(
                "official_mcp_servers.server._get_run_status_payload",
                return_value={
                    "status": "completed",
                    "run_id": "run-42",
                    "tool": "skill.decision.make",
                    "result": {"recommendation": "Proceed"},
                },
            ),
        ):
            from official_mcp_servers.server import call_tool

            start = await call_tool(
                "skill.decision.make",
                {"goal": "Choose infra approach", "_async": True},
            )
            start_parsed = json.loads(start[0].text)
            assert start_parsed["_run"]["status"] == "running"
            assert start_parsed["_run"]["run_id"] == "run-42"

            status = await call_tool("run.status", {"run_id": "run-42"})
            status_parsed = json.loads(status[0].text)
            assert status_parsed["status"] == "completed"
            assert status_parsed["result"]["recommendation"] == "Proceed"

    @pytest.mark.asyncio
    async def test_executes_skill_with_diagnostics(self):
        """_include_diagnostics=True should route through execute_with_meta and return meta block."""
        mock_result = {
            "outputs": {"decision": "Choose A", "rationale": "Best fit."},
            "meta": {
                "fallback_used": True,
                "fallback_steps_count": 1,
                "fallback_steps": [
                    {
                        "step_id": "justify_decision",
                        "uses": "decision.option.justify",
                        "binding_id": "python_decision_option_justify",
                        "primary_binding_id": "openapi_decision_option_justify_openai_chat",
                        "fallback_used": True,
                        "attempts_count": 2,
                        "attempt_failures": [
                            {
                                "binding_id": "openapi_decision_option_justify_openai_chat",
                                "error_type": "RuntimeError",
                                "error_message": "timeout",
                            }
                        ],
                    }
                ],
                "step_diagnostics": [],
            },
        }
        with (
            patch("sdk.embedded.list_capabilities", return_value=_MOCK_CAPABILITIES),
            patch("sdk.embedded.list_skills", return_value=_MOCK_SKILLS),
            patch(
                "sdk.embedded.execute_with_meta", return_value=mock_result
            ) as mock_exec,
        ):
            from official_mcp_servers.server import call_tool

            result = await call_tool(
                "skill.experiment.structured-decision",
                {
                    "topic": "Launch",
                    "options": ["A", "B"],
                    "_include_diagnostics": True,
                },
            )

        parsed = json.loads(result[0].text)
        assert parsed["outputs"]["decision"] == "Choose A"
        meta = parsed["meta"]
        assert meta["fallback_used"] is True
        assert len(meta["fallback_steps"]) == 1
        assert (
            meta["fallback_steps"][0]["primary_binding_id"]
            == "openapi_decision_option_justify_openai_chat"
        )
        mock_exec.assert_called_once_with(
            "experiment.structured-decision", {"topic": "Launch", "options": ["A", "B"]}
        )

    @pytest.mark.asyncio
    async def test_unknown_tool_raises_error(self):
        with (
            patch("sdk.embedded.list_capabilities", return_value=_MOCK_CAPABILITIES),
            patch("sdk.embedded.list_skills", return_value=_MOCK_SKILLS),
        ):
            from official_mcp_servers.server import call_tool

            with pytest.raises(ValueError, match="Unknown tool"):
                await call_tool("nonexistent.tool", {})

    @pytest.mark.asyncio
    async def test_execution_error_returns_error_json(self):
        """Execution errors should be returned as JSON, not raised."""
        with (
            patch("sdk.embedded.list_capabilities", return_value=_MOCK_CAPABILITIES),
            patch("sdk.embedded.list_skills", return_value=_MOCK_SKILLS),
            patch(
                "sdk.embedded.execute_capability",
                side_effect=RuntimeError("Binding not found"),
            ),
        ):
            from official_mcp_servers.server import call_tool

            result = await call_tool("text.content.summarize", {"text": "test"})

        parsed = json.loads(result[0].text)
        assert "error" in parsed
        assert "Binding not found" in parsed["error"]
        assert "code" in parsed

    @pytest.mark.asyncio
    async def test_none_arguments_treated_as_empty(self):
        mock_result = {"valid": True, "errors": []}
        with (
            patch("sdk.embedded.list_capabilities", return_value=_MOCK_CAPABILITIES),
            patch("sdk.embedded.list_skills", return_value=_MOCK_SKILLS),
            patch("sdk.embedded.execute_capability", return_value=mock_result),
        ):
            from official_mcp_servers.server import call_tool

            result = await call_tool("data.schema.validate", None)

        parsed = json.loads(result[0].text)
        assert parsed["valid"] is True

    @pytest.mark.asyncio
    async def test_contract_inspect_returns_canonical_contract(self):
        with (
            patch("sdk.embedded.list_capabilities", return_value=_MOCK_CAPABILITIES),
            patch("sdk.embedded.list_skills", return_value=_MOCK_SKILLS),
        ):
            from official_mcp_servers.server import call_tool

            result = await call_tool(
                "contract.inspect", {"capability_id": "data.schema.validate"}
            )

        parsed = json.loads(result[0].text)
        assert parsed["id"] == "data.schema.validate"
        assert sorted(parsed["required_inputs"]) == ["data", "schema"]
        assert "inputs" in parsed
        assert "outputs" in parsed

    @pytest.mark.asyncio
    async def test_contract_inspect_requires_capability_id(self):
        with (
            patch("sdk.embedded.list_capabilities", return_value=_MOCK_CAPABILITIES),
            patch("sdk.embedded.list_skills", return_value=_MOCK_SKILLS),
        ):
            from official_mcp_servers.server import call_tool

            result = await call_tool("contract.inspect", {})

        parsed = json.loads(result[0].text)
        assert "error" in parsed
        assert "capability_id" in parsed["error"]


# ────────────────────────────────────────────────────────────────
# JSON Schema generation integration
# ────────────────────────────────────────────────────────────────


class TestMCPSchemaIntegration:
    """Verify that MCP tools have correct JSON Schemas for various types."""

    @pytest.mark.asyncio
    async def test_object_inputs_have_type(self):
        with (
            patch("sdk.embedded.list_capabilities", return_value=_MOCK_CAPABILITIES),
            patch("sdk.embedded.list_skills", return_value=_MOCK_SKILLS),
        ):
            from official_mcp_servers.server import list_tools

            tools = await list_tools()

        validate = [t for t in tools if t.name == "data.schema.validate"][0]
        assert validate.inputSchema["properties"]["data"]["type"] == "object"
        assert validate.inputSchema["properties"]["schema"]["type"] == "object"

    @pytest.mark.asyncio
    async def test_required_fields_are_correct(self):
        with (
            patch("sdk.embedded.list_capabilities", return_value=_MOCK_CAPABILITIES),
            patch("sdk.embedded.list_skills", return_value=_MOCK_SKILLS),
        ):
            from official_mcp_servers.server import list_tools

            tools = await list_tools()

        validate = [t for t in tools if t.name == "data.schema.validate"][0]
        assert sorted(validate.inputSchema["required"]) == ["data", "schema"]


# ────────────────────────────────────────────────────────────────
# Server instantiation
# ────────────────────────────────────────────────────────────────


class TestServerInstantiation:
    """Verify the server object is created correctly."""

    def test_server_exists(self):
        from official_mcp_servers.server import server

        assert server.name == "agent-skills"

    def test_cache_reset(self):
        """reset_cache should clear and allow re-discovery."""
        from official_mcp_servers.server import reset_cache, reset_skills_cache
        from official_mcp_servers import server as srv_module

        reset_cache()
        reset_skills_cache()
        assert srv_module._capabilities_cache is None
        assert srv_module._skills_cache is None


# ────────────────────────────────────────────────────────────────
# Skill MCP exposure
# ────────────────────────────────────────────────────────────────


class TestSkillTools:
    """Tests for skill exposure as MCP tools."""

    @pytest.mark.asyncio
    async def test_skills_appear_with_prefix(self):
        with (
            patch("sdk.embedded.list_capabilities", return_value=_MOCK_CAPABILITIES),
            patch("sdk.embedded.list_skills", return_value=_MOCK_SKILLS),
        ):
            from official_mcp_servers.server import list_tools

            tools = await list_tools()

        names = {t.name for t in tools}
        assert "skill.experiment.structured-decision" in names
        assert "skill.research.question.answer" in names

    @pytest.mark.asyncio
    async def test_skill_tool_description_has_skill_marker(self):
        with (
            patch("sdk.embedded.list_capabilities", return_value=_MOCK_CAPABILITIES),
            patch("sdk.embedded.list_skills", return_value=_MOCK_SKILLS),
        ):
            from official_mcp_servers.server import list_tools

            tools = await list_tools()

        skill_tool = [
            t for t in tools if t.name == "skill.experiment.structured-decision"
        ][0]
        assert "[SKILL]" in skill_tool.description
        assert "structured decision" in skill_tool.description.lower()

    @pytest.mark.asyncio
    async def test_skill_tool_input_schema_has_required_inputs(self):
        with (
            patch("sdk.embedded.list_capabilities", return_value=_MOCK_CAPABILITIES),
            patch("sdk.embedded.list_skills", return_value=_MOCK_SKILLS),
        ):
            from official_mcp_servers.server import list_tools

            tools = await list_tools()

        skill_tool = [
            t for t in tools if t.name == "skill.experiment.structured-decision"
        ][0]
        schema = skill_tool.inputSchema
        assert schema["type"] == "object"
        assert "topic" in schema["properties"]
        assert "options" in schema["properties"]
        assert sorted(schema["required"]) == ["options", "topic"]
        assert schema["properties"]["options"]["type"] == "array"
        assert "items" in schema["properties"]["options"]

    @pytest.mark.asyncio
    async def test_executes_skill_via_prefix(self):
        mock_result = {"decision": "Option A", "rationale": "Best fit."}
        with (
            patch("sdk.embedded.list_capabilities", return_value=_MOCK_CAPABILITIES),
            patch("sdk.embedded.list_skills", return_value=_MOCK_SKILLS),
            patch("sdk.embedded.execute", return_value=mock_result) as mock_exec,
        ):
            from official_mcp_servers.server import call_tool

            result = await call_tool(
                "skill.experiment.structured-decision",
                {"topic": "Buy laptop", "options": ["A", "B"]},
            )

        parsed = json.loads(result[0].text)
        assert parsed["decision"] == "Option A"
        mock_exec.assert_called_once_with(
            "experiment.structured-decision",
            {"topic": "Buy laptop", "options": ["A", "B"]},
        )

    @pytest.mark.asyncio
    async def test_skill_execution_error_returns_error_json(self):
        with (
            patch("sdk.embedded.list_capabilities", return_value=_MOCK_CAPABILITIES),
            patch("sdk.embedded.list_skills", return_value=_MOCK_SKILLS),
            patch("sdk.embedded.execute", side_effect=RuntimeError("Step failed")),
        ):
            from official_mcp_servers.server import call_tool

            result = await call_tool(
                "skill.experiment.structured-decision",
                {"topic": "test", "options": []},
            )

        parsed = json.loads(result[0].text)
        assert "error" in parsed
        assert "Step failed" in parsed["error"]

    @pytest.mark.asyncio
    async def test_skill_inspect_returns_metadata(self):
        with (
            patch("sdk.embedded.list_capabilities", return_value=_MOCK_CAPABILITIES),
            patch("sdk.embedded.list_skills", return_value=_MOCK_SKILLS),
        ):
            from official_mcp_servers.server import call_tool

            result = await call_tool(
                "skill.inspect",
                {"skill_id": "research.question.answer"},
            )

        parsed = json.loads(result[0].text)
        assert parsed["id"] == "research.question.answer"
        assert "question" in parsed["inputs"]
        assert "answer" in parsed["outputs"]

    @pytest.mark.asyncio
    async def test_skill_inspect_requires_skill_id(self):
        with (
            patch("sdk.embedded.list_capabilities", return_value=_MOCK_CAPABILITIES),
            patch("sdk.embedded.list_skills", return_value=_MOCK_SKILLS),
        ):
            from official_mcp_servers.server import call_tool

            result = await call_tool("skill.inspect", {})

        parsed = json.loads(result[0].text)
        assert "error" in parsed
        assert "skill_id" in parsed["error"]

    @pytest.mark.asyncio
    async def test_skill_inspect_unknown_id_returns_error(self):
        with (
            patch("sdk.embedded.list_capabilities", return_value=_MOCK_CAPABILITIES),
            patch("sdk.embedded.list_skills", return_value=_MOCK_SKILLS),
        ):
            from official_mcp_servers.server import call_tool

            result = await call_tool("skill.inspect", {"skill_id": "nonexistent.skill"})

        parsed = json.loads(result[0].text)
        assert "error" in parsed
        assert "nonexistent.skill" in parsed["error"]

    @pytest.mark.asyncio
    async def test_skill_prefix_tool_not_confused_with_capability(self):
        """Ensure skill. prefix tools are routed to execute(), not execute_capability()."""
        mock_result = {"answer": "42", "sources": []}
        with (
            patch("sdk.embedded.list_capabilities", return_value=_MOCK_CAPABILITIES),
            patch("sdk.embedded.list_skills", return_value=_MOCK_SKILLS),
            patch("sdk.embedded.execute", return_value=mock_result) as mock_skill_exec,
            patch("sdk.embedded.execute_capability") as mock_cap_exec,
        ):
            from official_mcp_servers.server import call_tool

            await call_tool(
                "skill.research.question.answer",
                {"question": "What is 6x7?"},
            )

        mock_skill_exec.assert_called_once()
        mock_cap_exec.assert_not_called()


# __main__.py entry point
# ────────────────────────────────────────────────────────────────


class TestMainEntryPoint:
    """Verify __main__.py parses arguments correctly."""

    def test_default_stdio(self):
        from official_mcp_servers.__main__ import _parse_args

        args = _parse_args([])
        assert args.sse is False
        assert args.host == "0.0.0.0"
        assert args.port == 8765

    def test_sse_flag(self):
        from official_mcp_servers.__main__ import _parse_args

        args = _parse_args(["--sse", "--port", "9000"])
        assert args.sse is True
        assert args.port == 9000

    def test_custom_host(self):
        from official_mcp_servers.__main__ import _parse_args

        args = _parse_args(["--host", "127.0.0.1"])
        assert args.host == "127.0.0.1"

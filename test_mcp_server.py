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


@pytest.fixture(autouse=True)
def _reset_cache():
    """Reset the server's capability cache before each test."""
    from official_mcp_servers.server import reset_cache

    reset_cache()
    yield
    reset_cache()


# ────────────────────────────────────────────────────────────────
# list_tools tests
# ────────────────────────────────────────────────────────────────


class TestListTools:
    """Tests for the list_tools MCP handler."""

    @pytest.mark.asyncio
    async def test_lists_all_capabilities(self):
        """Server should list all capabilities from the runtime as MCP tools."""
        with patch("sdk.embedded.list_capabilities", return_value=_MOCK_CAPABILITIES):
            from official_mcp_servers.server import list_tools

            tools = await list_tools()

        assert len(tools) == 3
        names = {t.name for t in tools}
        assert "text.content.summarize" in names
        assert "data.schema.validate" in names
        assert "fs.file.read" in names

    @pytest.mark.asyncio
    async def test_tool_has_description(self):
        with patch("sdk.embedded.list_capabilities", return_value=_MOCK_CAPABILITIES):
            from official_mcp_servers.server import list_tools

            tools = await list_tools()

        summarize = [t for t in tools if t.name == "text.content.summarize"][0]
        assert "condensed" in summarize.description.lower()

    @pytest.mark.asyncio
    async def test_tool_has_input_schema(self):
        with patch("sdk.embedded.list_capabilities", return_value=_MOCK_CAPABILITIES):
            from official_mcp_servers.server import list_tools

            tools = await list_tools()

        summarize = [t for t in tools if t.name == "text.content.summarize"][0]
        schema = summarize.inputSchema
        assert schema["type"] == "object"
        assert "text" in schema["properties"]
        assert schema["required"] == ["text"]

    @pytest.mark.asyncio
    async def test_empty_capabilities_returns_empty_list(self):
        with patch("sdk.embedded.list_capabilities", return_value=[]):
            from official_mcp_servers.server import list_tools

            tools = await list_tools()

        assert tools == []


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
    async def test_unknown_tool_raises_error(self):
        with patch("sdk.embedded.list_capabilities", return_value=_MOCK_CAPABILITIES):
            from official_mcp_servers.server import call_tool

            with pytest.raises(ValueError, match="Unknown tool"):
                await call_tool("nonexistent.tool", {})

    @pytest.mark.asyncio
    async def test_execution_error_returns_error_json(self):
        """Execution errors should be returned as JSON, not raised."""
        with (
            patch("sdk.embedded.list_capabilities", return_value=_MOCK_CAPABILITIES),
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
            patch("sdk.embedded.execute_capability", return_value=mock_result),
        ):
            from official_mcp_servers.server import call_tool

            result = await call_tool("data.schema.validate", None)

        parsed = json.loads(result[0].text)
        assert parsed["valid"] is True


# ────────────────────────────────────────────────────────────────
# JSON Schema generation integration
# ────────────────────────────────────────────────────────────────


class TestMCPSchemaIntegration:
    """Verify that MCP tools have correct JSON Schemas for various types."""

    @pytest.mark.asyncio
    async def test_object_inputs_have_type(self):
        with patch("sdk.embedded.list_capabilities", return_value=_MOCK_CAPABILITIES):
            from official_mcp_servers.server import list_tools

            tools = await list_tools()

        validate = [t for t in tools if t.name == "data.schema.validate"][0]
        assert validate.inputSchema["properties"]["data"]["type"] == "object"
        assert validate.inputSchema["properties"]["schema"]["type"] == "object"

    @pytest.mark.asyncio
    async def test_required_fields_are_correct(self):
        with patch("sdk.embedded.list_capabilities", return_value=_MOCK_CAPABILITIES):
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
        from official_mcp_servers.server import reset_cache
        from official_mcp_servers import server as srv_module

        reset_cache()
        assert srv_module._capabilities_cache is None


# ────────────────────────────────────────────────────────────────
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

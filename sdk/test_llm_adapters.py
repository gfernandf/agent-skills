"""Tests for native LLM provider adapters (Anthropic, OpenAI, Gemini).

Validates that each adapter produces the exact format required by its
respective LLM provider, and that the execute_*_tool_call helpers
correctly invoke capabilities and return JSON strings.

Uses unittest.mock to avoid requiring the full runtime stack or LLM SDKs.
"""

from __future__ import annotations

import json
from unittest.mock import patch


# ────────────────────────────────────────────────────────────────
# Shared fixtures
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
        "outputs": {"summary": {"type": "string"}},
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
        "outputs": {"valid": {"type": "boolean"}, "errors": {"type": "array"}},
    },
]

_MOCK_RESULT = {"summary": "Short version."}


# ────────────────────────────────────────────────────────────────
# Anthropic adapter tests
# ────────────────────────────────────────────────────────────────


class TestAnthropicAdapter:
    """Tests for as_anthropic_tools() and execute_anthropic_tool_call()."""

    @patch("sdk.embedded.list_capabilities", return_value=_MOCK_CAPABILITIES)
    def test_returns_list_of_dicts(self, _mock):
        from sdk.embedded import as_anthropic_tools

        tools = as_anthropic_tools()
        assert isinstance(tools, list)
        assert len(tools) == 2
        assert all(isinstance(t, dict) for t in tools)

    @patch("sdk.embedded.list_capabilities", return_value=_MOCK_CAPABILITIES)
    def test_tool_has_correct_keys(self, _mock):
        from sdk.embedded import as_anthropic_tools

        tools = as_anthropic_tools()
        tool = tools[0]
        assert "name" in tool
        assert "description" in tool
        assert "input_schema" in tool

    @patch("sdk.embedded.list_capabilities", return_value=_MOCK_CAPABILITIES)
    def test_name_uses_underscores(self, _mock):
        from sdk.embedded import as_anthropic_tools

        tools = as_anthropic_tools()
        assert tools[0]["name"] == "text_content_summarize"
        assert tools[1]["name"] == "data_schema_validate"

    @patch("sdk.embedded.list_capabilities", return_value=_MOCK_CAPABILITIES)
    def test_input_schema_is_json_schema(self, _mock):
        from sdk.embedded import as_anthropic_tools

        tools = as_anthropic_tools()
        schema = tools[0]["input_schema"]
        assert schema["type"] == "object"
        assert "text" in schema["properties"]
        assert schema["required"] == ["text"]

    @patch("sdk.embedded.list_capabilities", return_value=_MOCK_CAPABILITIES)
    def test_filtered_capabilities(self, _mock):
        from sdk.embedded import as_anthropic_tools

        tools = as_anthropic_tools(["text.content.summarize"])
        assert len(tools) == 1
        assert tools[0]["name"] == "text_content_summarize"

    @patch("sdk.embedded.list_capabilities", return_value=_MOCK_CAPABILITIES)
    def test_none_returns_all(self, _mock):
        from sdk.embedded import as_anthropic_tools

        tools = as_anthropic_tools(None)
        assert len(tools) == 2

    @patch("sdk.embedded.execute_capability", return_value=_MOCK_RESULT)
    def test_execute_tool_call_success(self, mock_exec):
        from sdk.embedded import execute_anthropic_tool_call

        result = execute_anthropic_tool_call(
            "text_content_summarize", {"text": "Hello"}
        )
        assert isinstance(result, str)
        parsed = json.loads(result)
        assert parsed["summary"] == "Short version."
        mock_exec.assert_called_once_with("text.content.summarize", {"text": "Hello"})

    @patch(
        "sdk.embedded.execute_capability", side_effect=RuntimeError("Binding failed")
    )
    def test_execute_tool_call_error(self, _mock):
        from sdk.embedded import execute_anthropic_tool_call

        result = execute_anthropic_tool_call(
            "text_content_summarize", {"text": "Hello"}
        )
        parsed = json.loads(result)
        assert "error" in parsed
        assert "Binding failed" in parsed["error"]

    @patch("sdk.embedded.list_capabilities", return_value=_MOCK_CAPABILITIES)
    def test_tools_are_json_serializable(self, _mock):
        from sdk.embedded import as_anthropic_tools

        tools = as_anthropic_tools()
        serialized = json.dumps(tools)
        assert isinstance(serialized, str)


# ────────────────────────────────────────────────────────────────
# OpenAI adapter tests
# ────────────────────────────────────────────────────────────────


class TestOpenAIAdapter:
    """Tests for as_openai_tools() and execute_openai_tool_call()."""

    @patch("sdk.embedded.list_capabilities", return_value=_MOCK_CAPABILITIES)
    def test_returns_list_of_dicts(self, _mock):
        from sdk.embedded import as_openai_tools

        tools = as_openai_tools()
        assert isinstance(tools, list)
        assert len(tools) == 2

    @patch("sdk.embedded.list_capabilities", return_value=_MOCK_CAPABILITIES)
    def test_tool_has_type_function(self, _mock):
        from sdk.embedded import as_openai_tools

        tools = as_openai_tools()
        for tool in tools:
            assert tool["type"] == "function"
            assert "function" in tool

    @patch("sdk.embedded.list_capabilities", return_value=_MOCK_CAPABILITIES)
    def test_function_has_correct_keys(self, _mock):
        from sdk.embedded import as_openai_tools

        tools = as_openai_tools()
        func = tools[0]["function"]
        assert "name" in func
        assert "description" in func
        assert "parameters" in func

    @patch("sdk.embedded.list_capabilities", return_value=_MOCK_CAPABILITIES)
    def test_name_uses_underscores(self, _mock):
        from sdk.embedded import as_openai_tools

        tools = as_openai_tools()
        assert tools[0]["function"]["name"] == "text_content_summarize"

    @patch("sdk.embedded.list_capabilities", return_value=_MOCK_CAPABILITIES)
    def test_parameters_is_json_schema(self, _mock):
        from sdk.embedded import as_openai_tools

        tools = as_openai_tools()
        params = tools[0]["function"]["parameters"]
        assert params["type"] == "object"
        assert "text" in params["properties"]
        assert params["required"] == ["text"]

    @patch("sdk.embedded.list_capabilities", return_value=_MOCK_CAPABILITIES)
    def test_filtered_capabilities(self, _mock):
        from sdk.embedded import as_openai_tools

        tools = as_openai_tools(["data.schema.validate"])
        assert len(tools) == 1
        assert tools[0]["function"]["name"] == "data_schema_validate"

    @patch("sdk.embedded.list_capabilities", return_value=_MOCK_CAPABILITIES)
    def test_none_returns_all(self, _mock):
        from sdk.embedded import as_openai_tools

        tools = as_openai_tools(None)
        assert len(tools) == 2

    @patch("sdk.embedded.execute_capability", return_value=_MOCK_RESULT)
    def test_execute_tool_call_with_json_string(self, mock_exec):
        from sdk.embedded import execute_openai_tool_call

        args_json = json.dumps({"text": "Hello", "max_length": 20})
        result = execute_openai_tool_call("text_content_summarize", args_json)
        assert isinstance(result, str)
        parsed = json.loads(result)
        assert parsed["summary"] == "Short version."
        mock_exec.assert_called_once_with(
            "text.content.summarize", {"text": "Hello", "max_length": 20}
        )

    @patch(
        "sdk.embedded.execute_capability", side_effect=RuntimeError("Binding failed")
    )
    def test_execute_tool_call_error(self, _mock):
        from sdk.embedded import execute_openai_tool_call

        result = execute_openai_tool_call("text_content_summarize", '{"text": "Hi"}')
        parsed = json.loads(result)
        assert "error" in parsed

    def test_execute_tool_call_invalid_json(self):
        from sdk.embedded import execute_openai_tool_call

        result = execute_openai_tool_call("text_content_summarize", "not-valid-json{")
        parsed = json.loads(result)
        assert "error" in parsed
        assert "Invalid JSON" in parsed["error"]

    @patch("sdk.embedded.list_capabilities", return_value=_MOCK_CAPABILITIES)
    def test_tools_are_json_serializable(self, _mock):
        from sdk.embedded import as_openai_tools

        tools = as_openai_tools()
        serialized = json.dumps(tools)
        assert isinstance(serialized, str)


# ────────────────────────────────────────────────────────────────
# Gemini adapter tests
# ────────────────────────────────────────────────────────────────


class TestGeminiAdapter:
    """Tests for as_gemini_tools() and execute_gemini_tool_call()."""

    @patch("sdk.embedded.list_capabilities", return_value=_MOCK_CAPABILITIES)
    def test_returns_list_with_function_declarations(self, _mock):
        from sdk.embedded import as_gemini_tools

        tools = as_gemini_tools()
        assert isinstance(tools, list)
        assert len(tools) == 1
        assert "function_declarations" in tools[0]

    @patch("sdk.embedded.list_capabilities", return_value=_MOCK_CAPABILITIES)
    def test_declarations_count(self, _mock):
        from sdk.embedded import as_gemini_tools

        tools = as_gemini_tools()
        decls = tools[0]["function_declarations"]
        assert len(decls) == 2

    @patch("sdk.embedded.list_capabilities", return_value=_MOCK_CAPABILITIES)
    def test_declaration_has_correct_keys(self, _mock):
        from sdk.embedded import as_gemini_tools

        tools = as_gemini_tools()
        decl = tools[0]["function_declarations"][0]
        assert "name" in decl
        assert "description" in decl
        assert "parameters" in decl

    @patch("sdk.embedded.list_capabilities", return_value=_MOCK_CAPABILITIES)
    def test_name_uses_underscores(self, _mock):
        from sdk.embedded import as_gemini_tools

        tools = as_gemini_tools()
        decl = tools[0]["function_declarations"][0]
        assert decl["name"] == "text_content_summarize"

    @patch("sdk.embedded.list_capabilities", return_value=_MOCK_CAPABILITIES)
    def test_types_are_uppercase(self, _mock):
        from sdk.embedded import as_gemini_tools

        tools = as_gemini_tools()
        params = tools[0]["function_declarations"][0]["parameters"]
        assert params["type"] == "OBJECT"
        assert params["properties"]["text"]["type"] == "STRING"

    @patch("sdk.embedded.list_capabilities", return_value=_MOCK_CAPABILITIES)
    def test_required_fields(self, _mock):
        from sdk.embedded import as_gemini_tools

        tools = as_gemini_tools()
        params = tools[0]["function_declarations"][0]["parameters"]
        assert params["required"] == ["text"]

    @patch("sdk.embedded.list_capabilities", return_value=_MOCK_CAPABILITIES)
    def test_filtered_capabilities(self, _mock):
        from sdk.embedded import as_gemini_tools

        tools = as_gemini_tools(["text.content.summarize"])
        decls = tools[0]["function_declarations"]
        assert len(decls) == 1

    @patch("sdk.embedded.list_capabilities", return_value=_MOCK_CAPABILITIES)
    def test_none_returns_all(self, _mock):
        from sdk.embedded import as_gemini_tools

        tools = as_gemini_tools(None)
        decls = tools[0]["function_declarations"]
        assert len(decls) == 2

    @patch("sdk.embedded.execute_capability", return_value=_MOCK_RESULT)
    def test_execute_tool_call_success(self, mock_exec):
        from sdk.embedded import execute_gemini_tool_call

        result = execute_gemini_tool_call("text_content_summarize", {"text": "Hello"})
        assert isinstance(result, str)
        parsed = json.loads(result)
        assert parsed["summary"] == "Short version."
        mock_exec.assert_called_once_with("text.content.summarize", {"text": "Hello"})

    @patch(
        "sdk.embedded.execute_capability", side_effect=RuntimeError("Binding failed")
    )
    def test_execute_tool_call_error(self, _mock):
        from sdk.embedded import execute_gemini_tool_call

        result = execute_gemini_tool_call("text_content_summarize", {"text": "Hi"})
        parsed = json.loads(result)
        assert "error" in parsed

    @patch("sdk.embedded.list_capabilities", return_value=_MOCK_CAPABILITIES)
    def test_tools_are_json_serializable(self, _mock):
        from sdk.embedded import as_gemini_tools

        tools = as_gemini_tools()
        serialized = json.dumps(tools)
        assert isinstance(serialized, str)


# ────────────────────────────────────────────────────────────────
# Cross-adapter consistency tests
# ────────────────────────────────────────────────────────────────


class TestCrossAdapterConsistency:
    """Verify that all three adapters expose the same set of capabilities."""

    @patch("sdk.embedded.list_capabilities", return_value=_MOCK_CAPABILITIES)
    def test_all_adapters_same_count(self, _mock):
        from sdk.embedded import as_anthropic_tools, as_openai_tools, as_gemini_tools

        anthropic_tools = as_anthropic_tools()
        openai_tools = as_openai_tools()
        gemini_tools = as_gemini_tools()

        assert len(anthropic_tools) == 2
        assert len(openai_tools) == 2
        assert len(gemini_tools[0]["function_declarations"]) == 2

    @patch("sdk.embedded.list_capabilities", return_value=_MOCK_CAPABILITIES)
    def test_all_adapters_same_names(self, _mock):
        from sdk.embedded import as_anthropic_tools, as_openai_tools, as_gemini_tools

        a_names = {t["name"] for t in as_anthropic_tools()}
        o_names = {t["function"]["name"] for t in as_openai_tools()}
        g_names = {d["name"] for d in as_gemini_tools()[0]["function_declarations"]}

        assert a_names == o_names == g_names

    @patch("sdk.embedded.list_capabilities", return_value=_MOCK_CAPABILITIES)
    def test_filtered_list_consistent(self, _mock):
        from sdk.embedded import as_anthropic_tools, as_openai_tools, as_gemini_tools

        cap_filter = ["text.content.summarize"]
        a = as_anthropic_tools(cap_filter)
        o = as_openai_tools(cap_filter)
        g = as_gemini_tools(cap_filter)

        assert len(a) == 1
        assert len(o) == 1
        assert len(g[0]["function_declarations"]) == 1

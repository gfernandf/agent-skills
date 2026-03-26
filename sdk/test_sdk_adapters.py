"""Tests for SDK framework adapters (LangChain, CrewAI, AutoGen, Semantic Kernel).

Uses unittest.mock to avoid requiring external framework dependencies.
Validates the HTTP contract and tool-building logic of each adapter.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


# ────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────

BASE_URL = "http://localhost:8080"
CAP_ID = "text.content.summarize"

_MOCK_CAP_DESC = {"id": CAP_ID, "description": "Summarize text."}
_MOCK_EXEC_RESULT = {"summary": "Short version."}
_MOCK_LIST_RESULT = {"capabilities": [{"id": CAP_ID}]}


def _fake_response(json_data: dict, status: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = json_data
    resp.raise_for_status.return_value = None
    return resp


# ────────────────────────────────────────────────────────────────
# LangChain adapter
# ────────────────────────────────────────────────────────────────


class TestLangChainAdapter:
    """Tests for sdk/langchain_adapter.py."""

    @patch("sdk.langchain_adapter.requests")
    def test_build_tools_with_explicit_capabilities(self, mock_requests: MagicMock):
        """Build tools for a given list of capability ids."""
        # Stub the BaseTool import via a fake class
        fake_base_tool = type("BaseTool", (), {
            "__init_subclass__": classmethod(lambda cls, **kw: None),
            "name": "",
            "description": "",
        })
        fake_module = SimpleNamespace(BaseTool=fake_base_tool)
        with patch.dict("sys.modules", {"langchain_core": MagicMock(), "langchain_core.tools": fake_module}):
            mock_requests.get.return_value = _fake_response(_MOCK_CAP_DESC)
            mock_requests.post.return_value = _fake_response(_MOCK_EXEC_RESULT)

            from sdk.langchain_adapter import build_langchain_tools

            tools = build_langchain_tools(
                base_url=BASE_URL,
                capabilities=[CAP_ID],
                api_key="test-key",
            )

        assert len(tools) == 1
        tool = tools[0]
        assert CAP_ID.replace(".", "_") in getattr(tool, "name", "")

    @patch("sdk.langchain_adapter.requests")
    def test_auto_discover_capabilities(self, mock_requests: MagicMock):
        """When capabilities=None, adapter auto-discovers from server."""
        fake_base_tool = type("BaseTool", (), {
            "__init_subclass__": classmethod(lambda cls, **kw: None),
            "name": "",
            "description": "",
        })
        fake_module = SimpleNamespace(BaseTool=fake_base_tool)
        with patch.dict("sys.modules", {"langchain_core": MagicMock(), "langchain_core.tools": fake_module}):
            # First call: list capabilities; second: describe
            mock_requests.get.side_effect = [
                _fake_response(_MOCK_LIST_RESULT),
                _fake_response(_MOCK_CAP_DESC),
            ]

            from sdk.langchain_adapter import build_langchain_tools

            tools = build_langchain_tools(base_url=BASE_URL)

        assert len(tools) == 1
        # Verify discovery GET was called
        calls = mock_requests.get.call_args_list
        assert "/v1/capabilities" in calls[0].args[0]

    def test_import_error_without_langchain(self):
        """Adapter raises ImportError if langchain-core is not installed."""
        import sys
        saved = sys.modules.get("langchain_core")
        saved_tools = sys.modules.get("langchain_core.tools")
        sys.modules["langchain_core"] = None  # type: ignore
        sys.modules["langchain_core.tools"] = None  # type: ignore
        try:
            # Re-import to trigger the check
            with pytest.raises(ImportError, match="langchain-core"):
                from sdk.langchain_adapter import build_langchain_tools
                build_langchain_tools(capabilities=[CAP_ID])
        finally:
            if saved is not None:
                sys.modules["langchain_core"] = saved
            else:
                sys.modules.pop("langchain_core", None)
            if saved_tools is not None:
                sys.modules["langchain_core.tools"] = saved_tools
            else:
                sys.modules.pop("langchain_core.tools", None)


# ────────────────────────────────────────────────────────────────
# CrewAI adapter
# ────────────────────────────────────────────────────────────────


class TestCrewAIAdapter:
    """Tests for sdk/crewai_adapter.py."""

    @patch("sdk.crewai_adapter.requests")
    def test_build_tools(self, mock_requests: MagicMock):
        fake_base_tool = type("BaseTool", (), {
            "__init_subclass__": classmethod(lambda cls, **kw: None),
            "name": "",
            "description": "",
        })
        fake_module = SimpleNamespace(BaseTool=fake_base_tool)
        with patch.dict("sys.modules", {"crewai": MagicMock(), "crewai.tools": fake_module}):
            mock_requests.get.return_value = _fake_response(_MOCK_CAP_DESC)

            from sdk.crewai_adapter import build_crewai_tools

            tools = build_crewai_tools(
                base_url=BASE_URL,
                capabilities=[CAP_ID],
            )

        assert len(tools) == 1

    def test_import_error_without_crewai(self):
        import sys
        saved = sys.modules.get("crewai")
        saved_tools = sys.modules.get("crewai.tools")
        sys.modules["crewai"] = None  # type: ignore
        sys.modules["crewai.tools"] = None  # type: ignore
        try:
            with pytest.raises(ImportError, match="crewai"):
                from sdk.crewai_adapter import build_crewai_tools
                build_crewai_tools(capabilities=[CAP_ID])
        finally:
            if saved is not None:
                sys.modules["crewai"] = saved
            else:
                sys.modules.pop("crewai", None)
            if saved_tools is not None:
                sys.modules["crewai.tools"] = saved_tools
            else:
                sys.modules.pop("crewai.tools", None)


# ────────────────────────────────────────────────────────────────
# AutoGen adapter
# ────────────────────────────────────────────────────────────────


class TestAutoGenAdapter:
    """Tests for sdk/autogen_adapter.py."""

    @patch("sdk.autogen_adapter.requests")
    def test_build_tools_explicit(self, mock_requests: MagicMock):
        mock_requests.get.return_value = _fake_response(_MOCK_CAP_DESC)
        mock_requests.post.return_value = _fake_response(_MOCK_EXEC_RESULT)

        from sdk.autogen_adapter import build_autogen_tools

        tools = build_autogen_tools(
            base_url=BASE_URL,
            capabilities=[CAP_ID],
            api_key="key-123",
        )

        assert len(tools) == 1
        tool = tools[0]
        assert tool["name"] == CAP_ID.replace(".", "_")
        assert callable(tool["function"])
        assert isinstance(tool["description"], str)

    @patch("sdk.autogen_adapter.requests")
    def test_tool_function_calls_api(self, mock_requests: MagicMock):
        mock_requests.get.return_value = _fake_response(_MOCK_CAP_DESC)
        mock_requests.post.return_value = _fake_response(_MOCK_EXEC_RESULT)

        from sdk.autogen_adapter import build_autogen_tools

        tools = build_autogen_tools(base_url=BASE_URL, capabilities=[CAP_ID])
        result = tools[0]["function"](inputs={"text": "hello"})

        assert result == _MOCK_EXEC_RESULT
        mock_requests.post.assert_called_once()

    @patch("sdk.autogen_adapter.requests")
    def test_auto_discover(self, mock_requests: MagicMock):
        mock_requests.get.side_effect = [
            _fake_response(_MOCK_LIST_RESULT),
            _fake_response(_MOCK_CAP_DESC),
        ]

        from sdk.autogen_adapter import build_autogen_tools

        tools = build_autogen_tools(base_url=BASE_URL)
        assert len(tools) == 1


# ────────────────────────────────────────────────────────────────
# Semantic Kernel adapter
# ────────────────────────────────────────────────────────────────


class TestSemanticKernelAdapter:
    """Tests for sdk/semantic_kernel_adapter.py."""

    @patch("sdk.semantic_kernel_adapter.requests")
    def test_build_sk_functions(self, mock_requests: MagicMock):
        # Create real-looking fakes for SK
        def fake_kernel_function(**kwargs):
            def decorator(fn):
                fn._sk_name = kwargs.get("name", fn.__name__)
                fn._sk_desc = kwargs.get("description", "")
                return fn
            return decorator

        fake_kf_mod = SimpleNamespace(KernelFunction=type("KernelFunction", (), {}))
        fake_decorator_mod = SimpleNamespace(kernel_function=fake_kernel_function)
        fake_plugin_mod = SimpleNamespace(
            KernelFunction=fake_kf_mod.KernelFunction,
            KernelPlugin=type("KernelPlugin", (), {"__init__": lambda self, **kw: None}),
            kernel_function_decorator=fake_decorator_mod,
        )

        with patch.dict("sys.modules", {
            "semantic_kernel": MagicMock(),
            "semantic_kernel.functions": fake_plugin_mod,
            "semantic_kernel.functions.kernel_function_decorator": fake_decorator_mod,
        }):
            mock_requests.get.return_value = _fake_response(_MOCK_CAP_DESC)

            from sdk.semantic_kernel_adapter import build_sk_functions

            functions = build_sk_functions(base_url=BASE_URL, capabilities=[CAP_ID])

        assert len(functions) == 1

    @patch("sdk.semantic_kernel_adapter.requests")
    def test_build_sk_plugin(self, mock_requests: MagicMock):
        def fake_kernel_function(**kwargs):
            def decorator(fn):
                fn._sk_name = kwargs.get("name", fn.__name__)
                return fn
            return decorator

        fake_kf_mod = SimpleNamespace(KernelFunction=type("KernelFunction", (), {}))
        fake_decorator_mod = SimpleNamespace(kernel_function=fake_kernel_function)

        _plugin_instances = []

        class FakeKernelPlugin:
            def __init__(self, **kwargs):
                self.name = kwargs.get("name", "")
                self.functions = kwargs.get("functions", [])
                _plugin_instances.append(self)

        fake_plugin_mod = SimpleNamespace(
            KernelFunction=fake_kf_mod.KernelFunction,
            KernelPlugin=FakeKernelPlugin,
            kernel_function_decorator=fake_decorator_mod,
        )

        with patch.dict("sys.modules", {
            "semantic_kernel": MagicMock(),
            "semantic_kernel.functions": fake_plugin_mod,
            "semantic_kernel.functions.kernel_function_decorator": fake_decorator_mod,
        }):
            mock_requests.get.return_value = _fake_response(_MOCK_CAP_DESC)

            from sdk.semantic_kernel_adapter import build_sk_plugin

            plugin = build_sk_plugin(
                base_url=BASE_URL,
                capabilities=[CAP_ID],
                plugin_name="test_plugin",
            )

        assert plugin is not None


# ────────────────────────────────────────────────────────────────
# Cross-adapter: HTTP contract consistency
# ────────────────────────────────────────────────────────────────


class TestHTTPContract:
    """Verify all adapters use the same HTTP endpoint pattern."""

    @patch("sdk.langchain_adapter.requests")
    @patch("sdk.crewai_adapter.requests")
    @patch("sdk.autogen_adapter.requests")
    @patch("sdk.semantic_kernel_adapter.requests")
    def test_all_adapters_call_correct_endpoint(
        self, mock_sk, mock_autogen, mock_crewai, mock_langchain
    ):
        """All adapters POST to /v1/capabilities/{id}/execute."""
        for mock_req in [mock_langchain, mock_crewai, mock_autogen, mock_sk]:
            mock_req.get.return_value = _fake_response(_MOCK_CAP_DESC)
            mock_req.post.return_value = _fake_response(_MOCK_EXEC_RESULT)

        # Call each adapter's internal _call_capability
        from sdk.langchain_adapter import _call_capability as lc_call
        from sdk.crewai_adapter import _call_capability as crew_call
        from sdk.autogen_adapter import _call_capability as ag_call
        from sdk.semantic_kernel_adapter import _call_capability as sk_call

        for call_fn, mock_req in [
            (lc_call, mock_langchain),
            (crew_call, mock_crewai),
            (ag_call, mock_autogen),
            (sk_call, mock_sk),
        ]:
            call_fn(BASE_URL, CAP_ID, {"text": "hello"}, api_key="key")
            url_called = mock_req.post.call_args.args[0]
            assert url_called == f"{BASE_URL}/v1/capabilities/{CAP_ID}/execute"

    @patch("sdk.autogen_adapter.requests")
    def test_api_key_in_bearer_header(self, mock_requests: MagicMock):
        """All adapters send API key as Bearer token."""
        mock_requests.post.return_value = _fake_response(_MOCK_EXEC_RESULT)

        from sdk.autogen_adapter import _call_capability

        _call_capability(BASE_URL, CAP_ID, {}, api_key="secret-key")
        headers = mock_requests.post.call_args.kwargs.get("headers", {})
        assert headers.get("Authorization") == "Bearer secret-key"

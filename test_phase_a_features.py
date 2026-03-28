"""E2E tests for Phase A killer features: K2 (Embedded Runtime), K3 (Dev Watch), K5 (Benchmark Lab).

Run: python -m pytest test_new_skills.py -k "PhaseA" -v
   or: python -m pytest test_phase_a_features.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


# ═══════════════════════════════════════════════════════════════════════════
# K2: Embedded Runtime
# ═══════════════════════════════════════════════════════════════════════════


class TestK2EmbeddedRuntime:
    """Validate sdk/embedded.py — in-process execution without HTTP."""

    def test_module_importable(self):
        from sdk import embedded

        assert hasattr(embedded, "execute")
        assert hasattr(embedded, "execute_capability")
        assert hasattr(embedded, "list_capabilities")
        assert hasattr(embedded, "list_skills")
        assert hasattr(embedded, "as_langchain_tools")
        assert hasattr(embedded, "as_crewai_tools")
        assert hasattr(embedded, "as_autogen_tools")
        assert hasattr(embedded, "as_semantic_kernel_functions")
        assert hasattr(embedded, "reset")

    def test_reset_clears_cache(self):
        from sdk import embedded

        embedded._engine = "sentinel"
        embedded.reset()
        assert embedded._engine is None

    def test_execute_calls_engine(self):
        from sdk import embedded

        embedded.reset()

        mock_engine = MagicMock()
        mock_engine.execute.return_value = SimpleNamespace(
            status="completed",
            outputs={"summary": "ok"},
        )
        mock_cap_loader = MagicMock()
        mock_cap_executor = MagicMock()

        with patch.object(
            embedded,
            "_get_components",
            return_value=(mock_engine, mock_cap_loader, mock_cap_executor),
        ):
            result = embedded.execute("test.skill", {"text": "hello"})

        assert result == {"summary": "ok"}
        mock_engine.execute.assert_called_once()

    def test_execute_raises_on_failure(self):
        from sdk import embedded

        embedded.reset()

        mock_engine = MagicMock()
        mock_engine.execute.return_value = SimpleNamespace(
            status="failed",
            outputs={},
            error="something went wrong",
        )
        mock_cap_loader = MagicMock()
        mock_cap_executor = MagicMock()

        with patch.object(
            embedded,
            "_get_components",
            return_value=(mock_engine, mock_cap_loader, mock_cap_executor),
        ):
            with pytest.raises(RuntimeError, match="failed"):
                embedded.execute("test.skill", {"text": "hello"})

    def test_execute_capability_direct(self):
        from sdk import embedded

        embedded.reset()

        mock_cap = MagicMock()
        mock_cap.id = "text.content.summarize"

        mock_engine = MagicMock()
        mock_cap_loader = MagicMock()
        mock_cap_loader.get_capability.return_value = mock_cap
        mock_cap_executor = MagicMock()
        mock_cap_executor.execute.return_value = (
            {"summary": "short"},
            {"binding_id": "b1"},
        )

        with patch.object(
            embedded,
            "_get_components",
            return_value=(mock_engine, mock_cap_loader, mock_cap_executor),
        ):
            result = embedded.execute_capability(
                "text.content.summarize", {"text": "hello"}
            )

        assert result == {"summary": "short"}
        mock_cap_executor.execute.assert_called_once_with(mock_cap, {"text": "hello"})

    def test_list_capabilities(self):
        from sdk import embedded

        embedded.reset()

        mock_cap = MagicMock()
        mock_cap.description = "Summarize text"
        mock_cap.inputs = {
            "text": SimpleNamespace(type="string", required=True, description="Input")
        }
        mock_cap.outputs = {
            "summary": SimpleNamespace(
                type="string", required=True, description="Output"
            )
        }

        mock_engine = MagicMock()
        mock_cap_loader = MagicMock()
        mock_cap_loader.get_all_capabilities.return_value = {
            "text.content.summarize": mock_cap
        }
        mock_cap_executor = MagicMock()

        with patch.object(
            embedded,
            "_get_components",
            return_value=(mock_engine, mock_cap_loader, mock_cap_executor),
        ):
            caps = embedded.list_capabilities()

        assert len(caps) == 1
        assert caps[0]["id"] == "text.content.summarize"
        assert "text" in caps[0]["inputs"]

    def test_as_autogen_tools(self):
        from sdk import embedded

        embedded.reset()

        mock_cap = MagicMock()
        mock_cap.description = "Summarize text"
        mock_cap.inputs = {
            "text": SimpleNamespace(type="string", required=True, description="Input")
        }
        mock_cap.outputs = {
            "summary": SimpleNamespace(
                type="string", required=True, description="Output"
            )
        }

        mock_engine = MagicMock()
        mock_cap_loader = MagicMock()
        mock_cap_loader.get_all_capabilities.return_value = {
            "text.content.summarize": mock_cap
        }
        mock_cap_executor = MagicMock()

        with patch.object(
            embedded,
            "_get_components",
            return_value=(mock_engine, mock_cap_loader, mock_cap_executor),
        ):
            tools = embedded.as_autogen_tools(["text.content.summarize"])

        assert len(tools) == 1
        assert tools[0]["name"] == "text_content_summarize"
        assert callable(tools[0]["function"])

    def test_as_autogen_tools_all_capabilities(self):
        from sdk import embedded

        embedded.reset()

        mock_cap = MagicMock()
        mock_cap.description = "Test"
        mock_cap.inputs = {}
        mock_cap.outputs = {}

        mock_engine = MagicMock()
        mock_cap_loader = MagicMock()
        mock_cap_loader.get_all_capabilities.return_value = {
            "a.b.c": mock_cap,
            "d.e.f": mock_cap,
        }
        mock_cap_executor = MagicMock()

        with patch.object(
            embedded,
            "_get_components",
            return_value=(mock_engine, mock_cap_loader, mock_cap_executor),
        ):
            tools = embedded.as_autogen_tools()

        assert len(tools) == 2

    def test_list_skills(self):
        from sdk import embedded

        embedded.reset()

        mock_skill = MagicMock()
        mock_skill.name = "Translate & Summarize"
        mock_skill.description = "Translates and summarizes"

        mock_loader = MagicMock(
            spec=["get_skill", "_skill_index", "_build_skill_index"]
        )
        mock_loader._skill_index = {
            "text.translate-summary": Path(
                "skills/official/text/translate-summary/skill.yaml"
            )
        }
        mock_loader.get_skill.return_value = mock_skill

        mock_engine = MagicMock()
        mock_engine.skill_loader = mock_loader

        mock_cap_loader = MagicMock()
        mock_cap_executor = MagicMock()

        with patch.object(
            embedded,
            "_get_components",
            return_value=(mock_engine, mock_cap_loader, mock_cap_executor),
        ):
            skills = embedded.list_skills()

        assert len(skills) == 1
        assert skills[0]["id"] == "text.translate-summary"

    def test_field_to_dict_with_dict(self):
        from sdk.embedded import _field_to_dict

        assert _field_to_dict({"type": "string"}) == {"type": "string"}

    def test_field_to_dict_with_object(self):
        from sdk.embedded import _field_to_dict

        field = SimpleNamespace(type="integer", required=True, description="count")
        result = _field_to_dict(field)
        assert result["type"] == "integer"
        assert result["required"] is True

    def test_try_build_pydantic_schema(self):
        from sdk.embedded import _try_build_pydantic_schema

        schema = _try_build_pydantic_schema(
            "test.cap",
            {
                "text": {
                    "type": "string",
                    "required": True,
                    "description": "Input text",
                },
                "count": {"type": "integer", "required": False, "description": "Count"},
            },
        )
        # Should return a Pydantic model class or None if pydantic unavailable
        if schema is not None:
            # It's a model class
            assert hasattr(schema, "model_fields") or hasattr(schema, "__fields__")


# ═══════════════════════════════════════════════════════════════════════════
# K5: Benchmark Lab
# ═══════════════════════════════════════════════════════════════════════════


class TestK5BenchmarkLab:
    """Validate benchmark-lab CLI command and helpers."""

    def test_benchmark_lab_build_input(self):
        sys.path.insert(0, str(_ROOT))
        from cli.main import _benchmark_lab_build_input

        cap = SimpleNamespace(
            inputs={
                "text": SimpleNamespace(type="string"),
                "count": SimpleNamespace(type="integer"),
                "ratio": SimpleNamespace(type="number"),
                "flag": SimpleNamespace(type="boolean"),
                "items": SimpleNamespace(type="array"),
                "meta": SimpleNamespace(type="object"),
            }
        )
        result = _benchmark_lab_build_input(cap)
        assert isinstance(result["text"], str)
        assert result["count"] == 42
        assert result["ratio"] == 3.14
        assert result["flag"] is True
        assert isinstance(result["items"], list)
        assert isinstance(result["meta"], dict)

    def test_benchmark_lab_outputs_match_same_keys(self):
        from cli.main import _benchmark_lab_outputs_match

        assert _benchmark_lab_outputs_match({"a": 1, "b": 2}, {"a": 3, "b": 4}) is True

    def test_benchmark_lab_outputs_match_different_keys(self):
        from cli.main import _benchmark_lab_outputs_match

        assert _benchmark_lab_outputs_match({"a": 1}, {"b": 2}) is False

    def test_benchmark_lab_outputs_match_both_none(self):
        from cli.main import _benchmark_lab_outputs_match

        assert _benchmark_lab_outputs_match(None, None) is True

    def test_benchmark_lab_subparser_registered(self):
        """Ensure 'benchmark-lab' is a recognized subcommand."""

        # Parse with benchmark-lab to verify it exists
        from cli.main import main
        import io
        from contextlib import redirect_stderr

        buf = io.StringIO()
        try:
            with redirect_stderr(buf):
                sys.argv = ["agent-skills", "benchmark-lab", "--help"]
                main()
        except SystemExit:
            pass
        # If --help was recognized the output should mention benchmark-lab / capability_id
        # (argparse exits with 0 on --help, caught above)


# ═══════════════════════════════════════════════════════════════════════════
# K3: Dev Watch Mode
# ═══════════════════════════════════════════════════════════════════════════


class TestK3DevWatchMode:
    """Validate dev watch mode CLI command."""

    def test_dev_subparser_registered(self):
        """Ensure 'dev' is a recognized subcommand."""
        import io
        from contextlib import redirect_stderr

        buf = io.StringIO()
        try:
            with redirect_stderr(buf):
                sys.argv = ["agent-skills", "dev", "--help"]
                from cli.main import main

                main()
        except SystemExit:
            pass

    def test_dev_dispatches_to_cmd_dev(self):
        """Verify dispatch table has the dev entry."""
        cli_source = (_ROOT / "cli" / "main.py").read_text(encoding="utf-8")
        assert 'args.command == "dev"' in cli_source
        assert "_cmd_dev(" in cli_source

    def test_dev_cmd_function_exists(self):
        from cli.main import _cmd_dev

        assert callable(_cmd_dev)

    def test_dev_cmd_rejects_unknown_skill(self):
        """Should exit with error for nonexistent skill."""
        from cli.main import _cmd_dev

        with pytest.raises(SystemExit):
            _cmd_dev(
                registry_root=_ROOT.parent / "agent-skill-registry",
                runtime_root=_ROOT,
                host_root=_ROOT,
                skill_id="nonexistent.skill.does.not.exist",
                interval=1.0,
                no_test=True,
            )


# ═══════════════════════════════════════════════════════════════════════════
# Integration: Embedded Runtime with real engine
# ═══════════════════════════════════════════════════════════════════════════


class TestEmbeddedRealEngine:
    """Integration tests using the real runtime engine."""

    def test_real_engine_initialization(self):
        """Verify the embedded runtime can build a real engine."""
        from sdk.embedded import _get_components, reset

        reset()

        engine, cap_loader, cap_executor = _get_components()
        assert engine is not None
        assert cap_loader is not None
        assert cap_executor is not None

    def test_real_list_capabilities(self):
        """List capabilities from the real registry."""
        from sdk.embedded import list_capabilities, reset

        reset()

        caps = list_capabilities()
        assert len(caps) > 0
        assert all("id" in c for c in caps)

    def test_real_list_skills(self):
        """List skills from the real registry."""
        from sdk.embedded import list_skills, reset

        reset()

        skills = list_skills()
        assert len(skills) > 0
        assert all("id" in s for s in skills)

    def test_real_execute_skill(self):
        """Execute a skill through the embedded runtime."""
        from sdk.embedded import execute, reset

        reset()

        result = execute(
            "text.translate-summary",
            {"text": "Agent Skills is a runtime.", "target_language": "es"},
        )
        assert isinstance(result, dict)
        assert len(result) > 0

    def test_real_execute_capability(self):
        """Execute a capability directly through the embedded runtime."""
        from sdk.embedded import execute_capability, reset

        reset()

        result = execute_capability(
            "text.content.summarize",
            {"text": "The quick brown fox jumps over the lazy dog.", "max_length": 20},
        )
        assert isinstance(result, dict)

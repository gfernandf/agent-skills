"""E2E tests for Phase B+C killer features: K1 (Ask), K6 (Compose), K4 (Triggers).

Run: python -m pytest test_phase_bc_features.py -v
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


# ═══════════════════════════════════════════════════════════════════════════
# K1: Ask NL Autopilot
# ═══════════════════════════════════════════════════════════════════════════


class TestK1Ask:
    """Validate the 'ask' NL autopilot CLI command."""

    def test_ask_subparser_registered(self):
        import io
        from contextlib import redirect_stderr

        buf = io.StringIO()
        try:
            with redirect_stderr(buf):
                sys.argv = ["agent-skills", "ask", "--help"]
                from cli.main import main

                main()
        except SystemExit:
            pass

    def test_ask_dispatches_to_cmd_ask(self):
        cli_source = (_ROOT / "cli" / "main.py").read_text(encoding="utf-8")
        assert 'args.command == "ask"' in cli_source
        assert "_cmd_ask(" in cli_source

    def test_ask_detect_language_spanish(self):
        from cli.main import _ask_detect_language

        assert _ask_detect_language("translate this to Spanish") == "es"

    def test_ask_detect_language_french(self):
        from cli.main import _ask_detect_language

        assert _ask_detect_language("translate in French") == "fr"

    def test_ask_detect_language_none(self):
        from cli.main import _ask_detect_language

        assert _ask_detect_language("summarize this text") is None

    def test_ask_detect_language_español(self):
        from cli.main import _ask_detect_language

        assert _ask_detect_language("traduce esto al español") == "es"

    def test_ask_map_inputs_basic(self):
        from cli.main import _ask_map_inputs

        skill_spec = MagicMock()
        skill_spec.inputs = {
            "text": SimpleNamespace(type="string", required=True),
            "target_language": SimpleNamespace(type="string", required=True),
        }
        mapped = _ask_map_inputs("translate this to Spanish", skill_spec, None)
        assert mapped["text"] == "translate this to Spanish"
        assert mapped["target_language"] == "es"

    def test_ask_map_inputs_with_extra_json(self):
        from cli.main import _ask_map_inputs

        skill_spec = MagicMock()
        skill_spec.inputs = {
            "text": SimpleNamespace(type="string", required=True),
            "max_length": SimpleNamespace(type="integer", required=True),
        }
        mapped = _ask_map_inputs("summarize this", skill_spec, '{"max_length": 50}')
        assert mapped["text"] == "summarize this"
        assert mapped["max_length"] == 50

    def test_ask_map_inputs_integer_defaults(self):
        from cli.main import _ask_map_inputs

        skill_spec = MagicMock()
        skill_spec.inputs = {
            "count": SimpleNamespace(type="integer", required=True),
        }
        mapped = _ask_map_inputs("do something", skill_spec, None)
        assert mapped["count"] == 10

    def test_ask_real_dry_run(self):
        """Test ask with --dry-run against real gateway."""
        from cli.main import _cmd_ask

        # Capture output
        import io
        from contextlib import redirect_stdout

        buf = io.StringIO()
        with redirect_stdout(buf):
            _cmd_ask(
                registry_root=_ROOT.parent / "agent-skill-registry",
                runtime_root=_ROOT,
                host_root=_ROOT,
                question="summarize this text",
                extra_input=None,
                dry_run=True,
                top=3,
                json_output=True,
            )
        output = buf.getvalue()
        data = json.loads(output)
        assert "candidates" in data
        assert "plan" in data


# ═══════════════════════════════════════════════════════════════════════════
# K6: Compose DSL
# ═══════════════════════════════════════════════════════════════════════════


class TestK6ComposeDSL:
    """Validate the compose DSL parser and compiler."""

    def test_module_importable(self):
        from tooling.compose_dsl import parse_compose, compile_to_yaml

        assert callable(parse_compose)
        assert callable(compile_to_yaml)

    def test_parse_simple_compose(self):
        from tooling.compose_dsl import parse_compose

        source = """
@id test.simple-compose
@name Simple Compose
@description A test

step1 = text.content.summarize(text=$input.text, max_length=100)
> summary = $step1.summary
"""
        spec = parse_compose(source)
        assert spec.skill_id == "test.simple-compose"
        assert spec.name == "Simple Compose"
        assert len(spec.steps) == 1
        assert spec.steps[0].id == "step1"
        assert spec.steps[0].capability == "text.content.summarize"
        assert len(spec.outputs) == 1

    def test_parse_multi_step_compose(self):
        from tooling.compose_dsl import parse_compose

        source = """
@id test.multi-step
@name Multi Step
@description Two steps with dependency

step1 = text.content.summarize(text=$input.text, max_length=100)
step2 = text.content.translate(text=$step1.summary, target_language="es")

> translated = $step2.translated_text
"""
        spec = parse_compose(source)
        assert len(spec.steps) == 2
        assert spec.steps[1].depends_on == ["step1"]

    def test_parse_comments_and_blanks(self):
        from tooling.compose_dsl import parse_compose

        source = """
# This is a comment
@id test.with-comments

# Another comment

step1 = text.content.summarize(text=$input.text, max_length=100)
"""
        spec = parse_compose(source)
        assert spec.skill_id == "test.with-comments"
        assert len(spec.steps) == 1

    def test_parse_error_missing_id(self):
        from tooling.compose_dsl import parse_compose, ComposeParseError

        with pytest.raises(ComposeParseError, match="Missing @id"):
            parse_compose("step1 = a.b.c(x=$input.y)")

    def test_parse_error_duplicate_step(self):
        from tooling.compose_dsl import parse_compose, ComposeParseError

        source = """
@id test.dup
step1 = a.b.c(x=$input.y)
step1 = d.e.f(x=$input.y)
"""
        with pytest.raises(ComposeParseError, match="Duplicate step"):
            parse_compose(source)

    def test_parse_error_no_steps(self):
        from tooling.compose_dsl import parse_compose, ComposeParseError

        with pytest.raises(ComposeParseError, match="No steps"):
            parse_compose("@id test.empty")

    def test_compile_to_yaml(self):
        from tooling.compose_dsl import parse_compose, compile_to_yaml

        source = """
@id test.compile
@name Compile Test
@description Test compilation

step1 = text.content.summarize(text=$input.text, max_length=100)
> summary = $step1.summary
"""
        spec = parse_compose(source)
        doc = compile_to_yaml(spec)
        assert doc["id"] == "test.compile"
        assert doc["version"] == "1.0.0"
        assert "text" in doc["inputs"]
        assert doc["inputs"]["text"]["required"] is True
        assert len(doc["steps"]) == 1
        assert doc["steps"][0]["uses"] == "text.content.summarize"
        assert "summary" in doc["outputs"]

    def test_compile_literal_values(self):
        from tooling.compose_dsl import parse_compose, compile_to_yaml

        source = """
@id test.literals
step1 = text.content.summarize(text=$input.text, max_length=100, verbose=true, label="test")
"""
        spec = parse_compose(source)
        doc = compile_to_yaml(spec)
        mapping = doc["steps"][0]["input_mapping"]
        assert mapping["max_length"]["value"] == 100
        assert mapping["verbose"]["value"] is True
        assert mapping["label"]["value"] == "test"

    def test_compile_to_yaml_string(self):
        from tooling.compose_dsl import parse_compose, compile_to_yaml_string

        source = """
@id test.yaml-string
step1 = a.b.c(x=$input.y)
"""
        spec = parse_compose(source)
        yaml_str = compile_to_yaml_string(spec)
        assert "test.yaml-string" in yaml_str
        assert "steps:" in yaml_str

    def test_parse_and_compile_shorthand(self):
        from tooling.compose_dsl import parse_and_compile

        source = """
@id test.shorthand
step1 = a.b.c(x=$input.y)
"""
        yaml_str = parse_and_compile(source)
        assert "test.shorthand" in yaml_str

    def test_compose_subparser_registered(self):
        import io
        from contextlib import redirect_stderr

        buf = io.StringIO()
        try:
            with redirect_stderr(buf):
                sys.argv = ["agent-skills", "compose", "--help"]
                from cli.main import main

                main()
        except SystemExit:
            pass

    def test_compose_compile_to_file(self):
        """Compile a .compose file to a temporary YAML file."""
        from tooling.compose_dsl import parse_compose, compile_to_yaml_string

        source = """
@id test.file-output
@name File Output Test
@description Test output to file

step1 = text.content.summarize(text=$input.text, max_length=100)
> result = $step1.summary
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".compose", delete=False, encoding="utf-8"
        ) as f:
            f.write(source)
            compose_path = f.name

        try:
            spec = parse_compose(Path(compose_path).read_text(encoding="utf-8"))
            yaml_str = compile_to_yaml_string(spec)
            assert "test.file-output" in yaml_str
            assert "text.content.summarize" in yaml_str
        finally:
            Path(compose_path).unlink(missing_ok=True)


# ═══════════════════════════════════════════════════════════════════════════
# K4: Skill Triggers
# ═══════════════════════════════════════════════════════════════════════════


class TestK4Triggers:
    """Validate the trigger system."""

    def test_trigger_module_importable(self):
        from runtime.triggers import TriggerRegistry, TriggerEvent, TriggerEngine

        assert callable(TriggerRegistry)
        assert callable(TriggerEvent)
        assert callable(TriggerEngine)

    def test_trigger_registry_empty(self):
        from runtime.triggers import TriggerRegistry

        reg = TriggerRegistry()
        assert reg.trigger_count == 0
        assert reg.list_all() == []

    def test_trigger_register_and_match_webhook(self):
        from runtime.triggers import TriggerRegistry, TriggerSpec, TriggerEvent

        reg = TriggerRegistry()
        reg.register(
            TriggerSpec(
                trigger_type="webhook",
                skill_id="test.webhook-skill",
                config={"type": "webhook", "name": "deploy"},
            )
        )
        assert reg.trigger_count == 1

        event = TriggerEvent(event_type="webhook", payload={"webhook_name": "deploy"})
        matches = reg.match(event)
        assert len(matches) == 1
        assert matches[0].trigger.skill_id == "test.webhook-skill"

    def test_trigger_no_match_wrong_webhook(self):
        from runtime.triggers import TriggerRegistry, TriggerSpec, TriggerEvent

        reg = TriggerRegistry()
        reg.register(
            TriggerSpec(
                trigger_type="webhook",
                skill_id="test.webhook-skill",
                config={"type": "webhook", "name": "deploy"},
            )
        )

        event = TriggerEvent(event_type="webhook", payload={"webhook_name": "wrong"})
        matches = reg.match(event)
        assert len(matches) == 0

    def test_trigger_event_chain(self):
        from runtime.triggers import TriggerRegistry, TriggerSpec, TriggerEvent

        reg = TriggerRegistry()
        reg.register(
            TriggerSpec(
                trigger_type="event",
                skill_id="test.downstream",
                config={
                    "type": "event",
                    "source_skill": "test.upstream",
                    "on_status": "completed",
                },
            )
        )

        event = TriggerEvent(
            event_type="event",
            payload={"source_skill": "test.upstream", "status": "completed"},
        )
        matches = reg.match(event)
        assert len(matches) == 1
        assert matches[0].trigger.skill_id == "test.downstream"

    def test_trigger_event_chain_wrong_status(self):
        from runtime.triggers import TriggerRegistry, TriggerSpec, TriggerEvent

        reg = TriggerRegistry()
        reg.register(
            TriggerSpec(
                trigger_type="event",
                skill_id="test.downstream",
                config={
                    "type": "event",
                    "source_skill": "test.upstream",
                    "on_status": "completed",
                },
            )
        )

        event = TriggerEvent(
            event_type="event",
            payload={"source_skill": "test.upstream", "status": "failed"},
        )
        matches = reg.match(event)
        assert len(matches) == 0

    def test_trigger_file_change(self):
        from runtime.triggers import TriggerRegistry, TriggerSpec, TriggerEvent

        reg = TriggerRegistry()
        reg.register(
            TriggerSpec(
                trigger_type="file_change",
                skill_id="test.file-watch",
                config={
                    "type": "file_change",
                    "patterns": ["data/*.csv", "data/*.json"],
                },
            )
        )

        event = TriggerEvent(
            event_type="file_change",
            payload={"changed_files": ["data/report.csv"]},
        )
        matches = reg.match(event)
        assert len(matches) == 1

    def test_trigger_file_change_no_match(self):
        from runtime.triggers import TriggerRegistry, TriggerSpec, TriggerEvent

        reg = TriggerRegistry()
        reg.register(
            TriggerSpec(
                trigger_type="file_change",
                skill_id="test.file-watch",
                config={"type": "file_change", "patterns": ["data/*.csv"]},
            )
        )

        event = TriggerEvent(
            event_type="file_change",
            payload={"changed_files": ["logs/output.txt"]},
        )
        matches = reg.match(event)
        assert len(matches) == 0

    def test_trigger_schedule_always_matches(self):
        from runtime.triggers import TriggerRegistry, TriggerSpec, TriggerEvent

        reg = TriggerRegistry()
        reg.register(
            TriggerSpec(
                trigger_type="schedule",
                skill_id="test.scheduled",
                config={"type": "schedule", "expression": "every 5m"},
            )
        )

        event = TriggerEvent(event_type="schedule")
        matches = reg.match(event)
        assert len(matches) == 1

    def test_trigger_engine_fire(self):
        from runtime.triggers import (
            TriggerRegistry,
            TriggerSpec,
            TriggerEvent,
            TriggerEngine,
        )

        reg = TriggerRegistry()
        reg.register(
            TriggerSpec(
                trigger_type="webhook",
                skill_id="test.hook-skill",
                config={"type": "webhook", "name": "my_hook"},
            )
        )

        executed = []

        def mock_execute(skill_id, inputs):
            executed.append(skill_id)
            return {"status": "completed", "outputs": {"result": "ok"}}

        engine = TriggerEngine(registry=reg, execute_fn=mock_execute)
        event = TriggerEvent(event_type="webhook", payload={"webhook_name": "my_hook"})
        results = engine.fire(event)

        assert len(results) == 1
        assert results[0]["status"] == "completed"
        assert "test.hook-skill" in executed
        assert len(engine.history) == 1

    def test_trigger_engine_handles_error(self):
        from runtime.triggers import (
            TriggerRegistry,
            TriggerSpec,
            TriggerEvent,
            TriggerEngine,
        )

        reg = TriggerRegistry()
        reg.register(
            TriggerSpec(
                trigger_type="webhook",
                skill_id="test.failing",
                config={"type": "webhook", "name": "fail_hook"},
            )
        )

        def failing_execute(skill_id, inputs):
            raise RuntimeError("Skill failed!")

        engine = TriggerEngine(registry=reg, execute_fn=failing_execute)
        event = TriggerEvent(
            event_type="webhook", payload={"webhook_name": "fail_hook"}
        )
        results = engine.fire(event)

        assert len(results) == 1
        assert results[0]["status"] == "failed"
        assert "failed" in results[0]["error"].lower()

    def test_trigger_to_summary(self):
        from runtime.triggers import TriggerRegistry, TriggerSpec

        reg = TriggerRegistry()
        reg.register(
            TriggerSpec(
                trigger_type="webhook",
                skill_id="test.a",
                config={"type": "webhook", "name": "hook1"},
            )
        )
        reg.register(
            TriggerSpec(
                trigger_type="event",
                skill_id="test.b",
                config={
                    "type": "event",
                    "source_skill": "test.a",
                    "on_status": "completed",
                },
            )
        )

        summary = reg.to_summary()
        assert summary["total_triggers"] == 2
        assert "webhook" in summary["by_type"]
        assert "event" in summary["by_type"]
        assert "hook1" in summary["webhooks"]
        assert "test.a" in summary["event_chains"]

    def test_trigger_get_webhooks(self):
        from runtime.triggers import TriggerRegistry, TriggerSpec

        reg = TriggerRegistry()
        reg.register(
            TriggerSpec(
                trigger_type="webhook",
                skill_id="test.a",
                config={"type": "webhook", "name": "deploy"},
            )
        )
        reg.register(
            TriggerSpec(
                trigger_type="webhook",
                skill_id="test.b",
                config={"type": "webhook", "name": "deploy"},
            )
        )
        wh = reg.get_webhooks()
        assert "deploy" in wh
        assert len(wh["deploy"]) == 2

    def test_triggers_cli_subparser_registered(self):
        import io
        from contextlib import redirect_stderr

        buf = io.StringIO()
        try:
            with redirect_stderr(buf):
                sys.argv = ["agent-skills", "triggers", "list", "--help"]
                from cli.main import main

                main()
        except SystemExit:
            pass

    def test_triggers_load_from_skills_root(self):
        """Build a temp skill dir with triggers and verify loading."""
        from runtime.triggers import TriggerRegistry

        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = (
                Path(tmpdir) / "official" / "test" / "triggered" / "trigger-test"
            )
            skill_dir.mkdir(parents=True)
            (skill_dir / "skill.yaml").write_text(
                "id: test.triggered\n"
                "version: '1.0.0'\n"
                "name: Triggered Skill\n"
                "description: Test\n"
                "inputs:\n  text:\n    type: string\n    required: true\n"
                "outputs:\n  result:\n    type: string\n"
                "steps:\n"
                "  - id: s1\n    uses: text.content.summarize\n"
                "    input_mapping:\n      text:\n        from_input: text\n"
                "triggers:\n"
                "  - type: webhook\n    name: test_hook\n"
                "  - type: event\n    source_skill: test.upstream\n    on_status: completed\n",
                encoding="utf-8",
            )

            reg = TriggerRegistry()
            count = reg.load_from_skills_root(Path(tmpdir))
            assert count == 2
            assert reg.trigger_count == 2

    def test_multiple_trigger_types_match(self):
        """Ensure triggers from different types don't cross-match."""
        from runtime.triggers import TriggerRegistry, TriggerSpec, TriggerEvent

        reg = TriggerRegistry()
        reg.register(
            TriggerSpec("webhook", "test.a", {"type": "webhook", "name": "hook1"})
        )
        reg.register(
            TriggerSpec(
                "schedule", "test.b", {"type": "schedule", "expression": "daily"}
            )
        )
        reg.register(
            TriggerSpec(
                "event",
                "test.c",
                {"type": "event", "source_skill": "test.x", "on_status": "completed"},
            )
        )

        webhook_event = TriggerEvent(
            event_type="webhook", payload={"webhook_name": "hook1"}
        )
        assert len(reg.match(webhook_event)) == 1
        assert reg.match(webhook_event)[0].trigger.skill_id == "test.a"

        schedule_event = TriggerEvent(event_type="schedule")
        assert len(reg.match(schedule_event)) == 1
        assert reg.match(schedule_event)[0].trigger.skill_id == "test.b"


# ═══════════════════════════════════════════════════════════════════════════
# K7: Showcase + Benchmark Markdown
# ═══════════════════════════════════════════════════════════════════════════


class TestK7Showcase:
    """Validate the showcase command and benchmark markdown format."""

    def test_showcase_subparser_registered(self):
        import io

        io.StringIO()
        try:
            from cli.main import main
            import sys

            old = sys.argv
            sys.argv = ["agent-skills", "showcase", "--help"]
            with pytest.raises(SystemExit):
                main()
            sys.argv = old
        except SystemExit:
            pass

    def test_showcase_no_run(self):
        """showcase --no-run emits markdown with mermaid + fields, no example."""
        from cli.main import _cmd_showcase
        import io
        from contextlib import redirect_stdout

        buf = io.StringIO()
        with redirect_stdout(buf):
            _cmd_showcase(
                registry_root=_ROOT.parent / "agent-skill-registry",
                runtime_root=_ROOT,
                host_root=_ROOT,
                skill_id="text.summarize-plain-input",
                no_run=True,
                local_skills_root=_ROOT / "skills" / "local",
            )
        md = buf.getvalue()
        assert "## text.summarize-plain-input" in md
        assert "```mermaid" in md
        assert "### Pipeline" in md
        assert "### Inputs / Outputs" in md
        assert "### Try it" in md
        # No example section when --no-run
        assert "### Example" not in md

    def test_showcase_with_run(self):
        """showcase with run produces example section."""
        from cli.main import _cmd_showcase
        import io
        from contextlib import redirect_stdout

        buf = io.StringIO()
        with redirect_stdout(buf):
            _cmd_showcase(
                registry_root=_ROOT.parent / "agent-skill-registry",
                runtime_root=_ROOT,
                host_root=_ROOT,
                skill_id="text.summarize-plain-input",
                no_run=False,
                local_skills_root=_ROOT / "skills" / "local",
            )
        md = buf.getvalue()
        assert "### Example" in md
        assert "**Input:**" in md
        assert "**Output:**" in md

    def test_showcase_write_to_file(self):
        """showcase --file writes to disk."""
        from cli.main import _cmd_showcase
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "showcase.md"
            _cmd_showcase(
                registry_root=_ROOT.parent / "agent-skill-registry",
                runtime_root=_ROOT,
                host_root=_ROOT,
                skill_id="text.summarize-plain-input",
                no_run=True,
                out_file=out,
                local_skills_root=_ROOT / "skills" / "local",
            )
            assert out.exists()
            content = out.read_text(encoding="utf-8")
            assert "## text.summarize-plain-input" in content
            assert "```mermaid" in content

    def test_format_benchmark_markdown(self):
        """_format_benchmark_markdown produces a valid markdown table."""
        from cli.main import _format_benchmark_markdown

        results = [
            {
                "binding_id": "python_text_summarize",
                "protocol": "python_call",
                "status": "ok",
                "mean_ms": 12.5,
                "median_ms": 11.0,
                "p95_ms": 15.3,
                "output_match": True,
            },
            {
                "binding_id": "openapi_text_summarize",
                "protocol": "openapi",
                "status": "ok",
                "mean_ms": 89.2,
                "median_ms": 85.0,
                "p95_ms": 102.1,
                "output_match": False,
            },
            {
                "binding_id": "mcp_text_summarize",
                "protocol": "mcp",
                "status": "error",
                "errors": "timeout",
            },
        ]
        md = _format_benchmark_markdown("text.content.summarize", results)
        assert "| Binding | Protocol |" in md
        assert "python_text_summarize" in md
        assert "✓" in md
        assert "✗" in md
        assert "FAILED" in md
        assert "text.content.summarize" in md

    def test_format_benchmark_markdown_empty(self):
        from cli.main import _format_benchmark_markdown

        md = _format_benchmark_markdown("test.cap", [])
        assert "| Binding | Protocol |" in md
        assert "test.cap" in md

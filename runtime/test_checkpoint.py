"""Tests for runtime/checkpoint.py — round-trip serialization of ExecutionState."""

import json
import os
import tempfile
import unittest
from datetime import datetime, timezone

from runtime.checkpoint import dict_to_state, load_checkpoint, save_checkpoint, state_to_dict
from runtime.models import (
    ExecutionState,
    FrameState,
    OutputState,
    RuntimeEvent,
    StepResult,
    TraceMetrics,
    TraceState,
    TraceStep,
    WorkingState,
)


def _make_state() -> ExecutionState:
    """Build a fully-populated ExecutionState for testing."""
    now = datetime(2026, 3, 26, 12, 0, 0, tzinfo=timezone.utc)
    return ExecutionState(
        skill_id="text.simple-summarize",
        inputs={"text": "hello world", "max_length": 100},
        vars={"intermediate": "processed"},
        outputs={"summary": "hello"},
        step_results={
            "step-1": StepResult(
                step_id="step-1",
                uses="text.content.summarize",
                status="success",
                resolved_input={"text": "hello world"},
                produced_output={"summary": "hello"},
                started_at=now,
                finished_at=now,
                reads=("inputs.text",),
                writes=("outputs.summary",),
                latency_ms=42,
            ),
        },
        written_targets={"outputs.summary", "vars.intermediate"},
        events=[
            RuntimeEvent(
                type="step.start",
                message="Starting step-1",
                timestamp=now,
                step_id="step-1",
                trace_id="trace-abc",
            ),
        ],
        started_at=now,
        finished_at=now,
        status="success",
        trace_id="trace-abc",
        frame=FrameState(
            goal="Summarize input text",
            context={"source": "test"},
            assumptions=("input is English",),
            priority="normal",
        ),
        working=WorkingState(
            artifacts={"draft": "hello"},
            entities=[{"name": "greeting"}],
        ),
        output=OutputState(
            result="hello",
            result_type="text",
            summary="Summarized text",
        ),
        trace=TraceState(
            steps=[
                TraceStep(
                    step_id="step-1",
                    capability_id="text.content.summarize",
                    status="success",
                    started_at=now,
                    ended_at=now,
                    reads=("inputs.text",),
                    writes=("outputs.summary",),
                    latency_ms=42,
                ),
            ],
            metrics=TraceMetrics(
                step_count=1, llm_calls=1, tokens_in=10, tokens_out=5, elapsed_ms=42
            ),
        ),
        extensions={"custom": {"key": "value"}},
        state_version="1.0.0",
        skill_version="0.1.0",
        iteration=1,
        current_step="step-1",
        parent_run_id="parent-xyz",
        updated_at=now,
    )


class TestCheckpointRoundTrip(unittest.TestCase):
    def test_round_trip_dict(self):
        """state → dict → state preserves all fields."""
        original = _make_state()
        d = state_to_dict(original)
        restored = dict_to_state(d)

        self.assertEqual(restored.skill_id, original.skill_id)
        self.assertEqual(restored.inputs, original.inputs)
        self.assertEqual(restored.vars, original.vars)
        self.assertEqual(restored.outputs, original.outputs)
        self.assertEqual(restored.status, original.status)
        self.assertEqual(restored.trace_id, original.trace_id)
        self.assertEqual(restored.started_at, original.started_at)
        self.assertEqual(restored.finished_at, original.finished_at)
        self.assertEqual(restored.written_targets, original.written_targets)
        self.assertEqual(restored.iteration, original.iteration)
        self.assertEqual(restored.current_step, original.current_step)
        self.assertEqual(restored.parent_run_id, original.parent_run_id)
        self.assertEqual(restored.extensions, original.extensions)
        self.assertEqual(restored.state_version, original.state_version)
        self.assertEqual(restored.skill_version, original.skill_version)

    def test_step_results_preserved(self):
        original = _make_state()
        restored = dict_to_state(state_to_dict(original))
        sr = restored.step_results["step-1"]
        self.assertEqual(sr.step_id, "step-1")
        self.assertEqual(sr.status, "success")
        self.assertEqual(sr.reads, ("inputs.text",))
        self.assertEqual(sr.writes, ("outputs.summary",))
        self.assertEqual(sr.latency_ms, 42)

    def test_cognitive_state_preserved(self):
        original = _make_state()
        restored = dict_to_state(state_to_dict(original))
        self.assertEqual(restored.frame.goal, "Summarize input text")
        self.assertEqual(restored.frame.assumptions, ("input is English",))
        self.assertEqual(restored.working.artifacts, {"draft": "hello"})
        self.assertEqual(restored.output.result_type, "text")
        self.assertEqual(restored.trace.metrics.llm_calls, 1)
        self.assertEqual(len(restored.trace.steps), 1)

    def test_events_preserved(self):
        original = _make_state()
        restored = dict_to_state(state_to_dict(original))
        self.assertEqual(len(restored.events), 1)
        self.assertEqual(restored.events[0].type, "step.start")
        self.assertEqual(restored.events[0].step_id, "step-1")

    def test_json_serializable(self):
        d = state_to_dict(_make_state())
        text = json.dumps(d)
        self.assertIsInstance(text, str)

    def test_file_round_trip(self):
        original = _make_state()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "checkpoint.json")
            save_checkpoint(original, path)
            restored = load_checkpoint(path)
        self.assertEqual(restored.skill_id, original.skill_id)
        self.assertEqual(restored.status, original.status)
        self.assertEqual(restored.trace_id, original.trace_id)

    def test_minimal_state(self):
        """A bare-minimum state still round-trips cleanly."""
        state = ExecutionState(
            skill_id="noop",
            inputs={},
            vars={},
            outputs={},
            step_results={},
            written_targets=set(),
            events=[],
        )
        restored = dict_to_state(state_to_dict(state))
        self.assertEqual(restored.skill_id, "noop")
        self.assertEqual(restored.status, "pending")


if __name__ == "__main__":
    unittest.main()

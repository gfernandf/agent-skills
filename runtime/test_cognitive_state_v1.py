"""
Integration tests for CognitiveState v1.

Tests the NEW functionality introduced in the upgrade:
- FrameState creation and read via resolver
- WorkingState writing (artifacts, cognitive slots)
- OutputState writing
- Extensions writing
- Merge strategies: append, deep_merge, replace
- Path traversal (nested reads and writes)
- Trace enrichment (TraceStep, TraceMetrics)
- Mixed legacy + cognitive mode
- Data lineage (reads/writes on StepResult)
- Read-only enforcement (frame, inputs, trace)

Run: python -m runtime.test_cognitive_state_v1
"""

from __future__ import annotations


from runtime.errors import (
    InvalidSkillSpecError,
    OutputMappingError,
    ReferenceResolutionError,
)
from runtime.execution_planner import ExecutionPlanner
from runtime.execution_state import (
    create_execution_state,
    mark_finished,
    mark_started,
)
from runtime.input_mapper import build_step_input
from runtime.models import (
    FieldSpec,
    FrameState,
    SkillSpec,
    StepSpec,
    TraceMetrics,
    TraceState,
    TraceStep,
)
from runtime.output_mapper import apply_step_output
from runtime.reference_resolver import ReferenceResolver


# ════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════


def _make_step(
    step_id: str = "s1",
    uses: str = "test.cap",
    input_mapping: dict | None = None,
    output_mapping: dict | None = None,
    config: dict | None = None,
) -> StepSpec:
    return StepSpec(
        id=step_id,
        uses=uses,
        input_mapping=input_mapping or {},
        output_mapping=output_mapping or {},
        config=config or {},
    )


def _make_skill(
    skill_id: str = "test.skill",
    steps: list[StepSpec] | None = None,
) -> SkillSpec:
    return SkillSpec(
        id=skill_id,
        version="1.0.0",
        name="Test",
        description="",
        inputs={"text": FieldSpec(type="string", required=True)},
        outputs={"result": FieldSpec(type="string", required=True)},
        steps=tuple(steps or [_make_step(output_mapping={"r": "outputs.result"})]),
        metadata={},
    )


_passed = 0
_failed = 0
_errors: list[str] = []


def _assert(condition: bool, msg: str) -> None:
    global _passed, _failed
    if condition:
        _passed += 1
    else:
        _failed += 1
        _errors.append(msg)
        print(f"  FAIL: {msg}")


def _assert_raises(exc_type, fn, msg: str) -> None:
    global _passed, _failed
    try:
        fn()
        _failed += 1
        _errors.append(f"{msg} (no exception raised)")
        print(f"  FAIL: {msg} (no exception raised)")
    except exc_type:
        _passed += 1
    except Exception as e:
        _failed += 1
        _errors.append(f"{msg} (wrong: {type(e).__name__}: {e})")
        print(f"  FAIL: {msg} (wrong: {type(e).__name__})")


# ════════════════════════════════════════════════════════════════
# 1. FrameState creation and resolution
# ════════════════════════════════════════════════════════════════


def test_frame_state():
    print("▸ FrameState creation and resolution")

    frame = FrameState(
        goal="Summarize document",
        context={"language": "es", "domain": "legal"},
        constraints={"max_tokens": 500},
        success_criteria={"coverage": 0.9},
        assumptions=("input is UTF-8", "single document"),
        priority="high",
    )
    state = create_execution_state("s1", {"text": "doc"}, frame=frame)

    _assert(state.frame.goal == "Summarize document", "frame.goal set")
    _assert(state.frame.context["language"] == "es", "frame.context populated")
    _assert(state.frame.constraints["max_tokens"] == 500, "frame.constraints populated")
    _assert(state.frame.priority == "high", "frame.priority set")
    _assert(
        state.frame.assumptions == ("input is UTF-8", "single document"),
        "frame.assumptions tuple",
    )

    # Resolver reads
    resolver = ReferenceResolver()
    _assert(
        resolver.resolve("frame.goal", state) == "Summarize document",
        "resolve frame.goal",
    )
    _assert(
        resolver.resolve("frame.context.language", state) == "es",
        "resolve frame.context.language",
    )
    _assert(
        resolver.resolve("frame.constraints.max_tokens", state) == 500,
        "resolve frame.constraints.max_tokens",
    )
    _assert(
        resolver.resolve("frame.priority", state) == "high", "resolve frame.priority"
    )
    _assert(
        resolver.resolve("frame.context.missing", state) is None,
        "resolve frame permissive on missing key",
    )
    _assert(
        resolver.resolve("frame.nonexistent", state) is None,
        "resolve frame permissive on missing attr",
    )

    # Default frame
    state2 = create_execution_state("s2", {})
    _assert(state2.frame.goal is None, "default frame.goal is None")
    _assert(state2.frame.context == {}, "default frame.context is empty")


# ════════════════════════════════════════════════════════════════
# 2. WorkingState write + read
# ════════════════════════════════════════════════════════════════


def test_working_state():
    print("▸ WorkingState write + read")

    resolver = ReferenceResolver()
    state = create_execution_state("s1", {"text": "hello"})

    # Write to working.artifacts.summary
    step = _make_step(output_mapping={"summary": "working.artifacts.summary"})
    apply_step_output(step, {"summary": "A brief summary"}, state)
    _assert(
        state.working.artifacts["summary"] == "A brief summary",
        "write working.artifacts.summary",
    )

    # Read back
    _assert(
        resolver.resolve("working.artifacts.summary", state) == "A brief summary",
        "resolve working.artifacts.summary",
    )

    # Write to working.artifacts with nested path
    step2 = _make_step(
        step_id="s2", output_mapping={"data": "working.artifacts.analysis.score"}
    )
    apply_step_output(step2, {"data": 0.95}, state)
    _assert(
        state.working.artifacts["analysis"]["score"] == 0.95,
        "nested write creates intermediate dicts",
    )
    _assert(
        resolver.resolve("working.artifacts.analysis.score", state) == 0.95,
        "resolve nested working path",
    )

    # Strict: error on missing working key
    _assert_raises(
        ReferenceResolutionError,
        lambda: resolver.resolve("working.artifacts.nonexistent", state),
        "working strict: error on missing key",
    )


# ════════════════════════════════════════════════════════════════
# 3. Cognitive slots (entities, risks, etc.)
# ════════════════════════════════════════════════════════════════


def test_cognitive_slots():
    print("▸ cognitive slots (entities, risks, hypotheses, etc.)")

    resolver = ReferenceResolver()
    state = create_execution_state("s1", {})

    # Write risks via append
    step = _make_step(
        output_mapping={"risks": "working.risks"}, config={"merge_strategy": "append"}
    )
    apply_step_output(
        step, {"risks": [{"label": "data loss", "severity": "high"}]}, state
    )
    _assert(len(state.working.risks) == 1, "append creates risks list")
    _assert(state.working.risks[0]["label"] == "data loss", "risk item correct")

    # Append more
    step2 = _make_step(
        step_id="s2",
        output_mapping={"risks": "working.risks"},
        config={"merge_strategy": "append"},
    )
    apply_step_output(
        step2, {"risks": [{"label": "timeout", "severity": "medium"}]}, state
    )
    _assert(len(state.working.risks) == 2, "append extends risks list")

    # Read via resolver
    _assert(
        resolver.resolve("working.risks", state) == state.working.risks,
        "resolve working.risks",
    )
    _assert(
        resolver.resolve("working.risks.0.label", state) == "data loss",
        "resolve working.risks.0.label",
    )
    _assert(
        resolver.resolve("working.risks.1.severity", state) == "medium",
        "resolve working.risks.1.severity",
    )

    # Same with entities
    step3 = _make_step(
        step_id="s3",
        output_mapping={"ents": "working.entities"},
        config={"merge_strategy": "append"},
    )
    apply_step_output(step3, {"ents": [{"name": "ACME", "type": "org"}]}, state)
    _assert(state.working.entities[0]["name"] == "ACME", "entities append works")

    # Hypotheses
    step4 = _make_step(
        step_id="s4",
        output_mapping={"hyp": "working.hypotheses"},
        config={"merge_strategy": "append"},
    )
    apply_step_output(
        step4, {"hyp": [{"claim": "Revenue growing", "confidence": 0.8}]}, state
    )
    _assert(state.working.hypotheses[0]["confidence"] == 0.8, "hypotheses append works")

    # Criteria
    step5 = _make_step(
        step_id="s5",
        output_mapping={"crit": "working.criteria"},
        config={"merge_strategy": "append"},
    )
    apply_step_output(step5, {"crit": [{"name": "accuracy", "weight": 0.7}]}, state)
    _assert(state.working.criteria[0]["weight"] == 0.7, "criteria append works")

    # Evidence
    step6 = _make_step(
        step_id="s6",
        output_mapping={"ev": "working.evidence"},
        config={"merge_strategy": "append"},
    )
    apply_step_output(
        step6, {"ev": [{"source": "doc1", "fact": "Q3 revenue up 15%"}]}, state
    )
    _assert(state.working.evidence[0]["source"] == "doc1", "evidence append works")

    # Options
    step7 = _make_step(
        step_id="s7",
        output_mapping={"opts": "working.options"},
        config={"merge_strategy": "append"},
    )
    apply_step_output(
        step7, {"opts": [{"id": "opt1", "description": "Expand team"}]}, state
    )
    _assert(state.working.options[0]["id"] == "opt1", "options append works")

    # Uncertainties
    step8 = _make_step(
        step_id="s8",
        output_mapping={"unc": "working.uncertainties"},
        config={"merge_strategy": "append"},
    )
    apply_step_output(step8, {"unc": [{"area": "market", "level": "high"}]}, state)
    _assert(
        state.working.uncertainties[0]["area"] == "market", "uncertainties append works"
    )

    # Intermediate decisions
    step9 = _make_step(
        step_id="s9",
        output_mapping={"dec": "working.intermediate_decisions"},
        config={"merge_strategy": "append"},
    )
    apply_step_output(
        step9, {"dec": [{"decision": "Focus on Q3", "rationale": "Most recent"}]}, state
    )
    _assert(
        state.working.intermediate_decisions[0]["decision"] == "Focus on Q3",
        "intermediate_decisions append works",
    )

    # Messages
    step10 = _make_step(
        step_id="s10",
        output_mapping={"msgs": "working.messages"},
        config={"merge_strategy": "append"},
    )
    apply_step_output(
        step10, {"msgs": [{"role": "assistant", "content": "Analysis complete"}]}, state
    )
    _assert(state.working.messages[0]["role"] == "assistant", "messages append works")


# ════════════════════════════════════════════════════════════════
# 4. OutputState
# ════════════════════════════════════════════════════════════════


def test_output_state():
    print("▸ OutputState write + read")

    resolver = ReferenceResolver()
    state = create_execution_state("s1", {})

    # Write to output.summary
    step = _make_step(output_mapping={"brief": "output.summary"})
    apply_step_output(step, {"brief": "Executive summary here"}, state)
    _assert(state.output.summary == "Executive summary here", "write output.summary")

    # Write to output.result
    step2 = _make_step(step_id="s2", output_mapping={"r": "output.result"})
    apply_step_output(step2, {"r": {"key": "findings"}}, state)
    _assert(state.output.result == {"key": "findings"}, "write output.result")

    # Write to output.status_reason
    step3 = _make_step(step_id="s3", output_mapping={"reason": "output.status_reason"})
    apply_step_output(step3, {"reason": "All criteria met"}, state)
    _assert(
        state.output.status_reason == "All criteria met", "write output.status_reason"
    )

    # Read via resolver (permissive)
    _assert(
        resolver.resolve("output.summary", state) == "Executive summary here",
        "resolve output.summary",
    )
    _assert(
        resolver.resolve("output.result_type", state) is None,
        "resolve output.result_type None (permissive)",
    )


# ════════════════════════════════════════════════════════════════
# 5. Extensions
# ════════════════════════════════════════════════════════════════


def test_extensions():
    print("▸ extensions write + read")

    resolver = ReferenceResolver()
    state = create_execution_state("s1", {})

    # Write to extensions.policy.approved
    step = _make_step(output_mapping={"v": "extensions.policy.approved"})
    apply_step_output(step, {"v": True}, state)
    _assert(
        state.extensions["policy"]["approved"] is True,
        "write extensions.policy.approved",
    )

    # Read
    _assert(
        resolver.resolve("extensions.policy.approved", state) is True,
        "resolve extensions.policy.approved",
    )
    _assert(
        resolver.resolve("extensions.missing.key", state) is None,
        "resolve extensions permissive",
    )

    # Deep merge
    step2 = _make_step(
        step_id="s2",
        output_mapping={"v": "extensions.policy"},
        config={"merge_strategy": "deep_merge"},
    )
    apply_step_output(step2, {"v": {"score": 0.9, "approved": False}}, state)
    _assert(state.extensions["policy"]["score"] == 0.9, "deep_merge adds key")
    _assert(
        state.extensions["policy"]["approved"] is False, "deep_merge overwrites key"
    )


# ════════════════════════════════════════════════════════════════
# 6. Merge strategies
# ════════════════════════════════════════════════════════════════


def test_merge_strategies():
    print("▸ merge strategies")

    # ── APPEND ──
    state = create_execution_state("s1", {})
    s1 = _make_step(step_id="s1", output_mapping={"items": "vars.list"})
    apply_step_output(s1, {"items": [1, 2]}, state)
    s2 = _make_step(
        step_id="s2",
        output_mapping={"items": "vars.list"},
        config={"merge_strategy": "append"},
    )
    apply_step_output(s2, {"items": [3, 4]}, state)
    _assert(state.vars["list"] == [1, 2, 3, 4], "append on vars works")

    # Append error: value not list
    state2 = create_execution_state("s1", {})
    s3 = _make_step(step_id="s3", output_mapping={"v": "vars.x"})
    apply_step_output(s3, {"v": [1]}, state2)
    s4 = _make_step(
        step_id="s4",
        output_mapping={"v": "vars.x"},
        config={"merge_strategy": "append"},
    )
    _assert_raises(
        OutputMappingError,
        lambda: apply_step_output(s4, {"v": "not a list"}, state2),
        "append rejects non-list value",
    )

    # ── DEEP_MERGE ──
    state = create_execution_state("s1", {})
    s1 = _make_step(step_id="s1", output_mapping={"d": "vars.config"})
    apply_step_output(s1, {"d": {"a": 1, "nested": {"x": 10}}}, state)
    s2 = _make_step(
        step_id="s2",
        output_mapping={"d": "vars.config"},
        config={"merge_strategy": "deep_merge"},
    )
    apply_step_output(s2, {"d": {"b": 2, "nested": {"y": 20}}}, state)
    _assert(state.vars["config"]["a"] == 1, "deep_merge preserves existing")
    _assert(state.vars["config"]["b"] == 2, "deep_merge adds new")
    _assert(state.vars["config"]["nested"]["x"] == 10, "deep_merge nested preserves")
    _assert(state.vars["config"]["nested"]["y"] == 20, "deep_merge nested adds")

    # ── REPLACE ──
    state = create_execution_state("s1", {})
    s1 = _make_step(step_id="s1", output_mapping={"v": "vars.x"})
    apply_step_output(s1, {"v": "first"}, state)
    s2 = _make_step(
        step_id="s2",
        output_mapping={"v": "vars.x"},
        config={"merge_strategy": "replace"},
    )
    apply_step_output(s2, {"v": "second"}, state)
    _assert(state.vars["x"] == "second", "replace overwrites without error")

    # ── OVERWRITE duplicate error ──
    state = create_execution_state("s1", {})
    s1 = _make_step(step_id="s1", output_mapping={"v": "vars.x"})
    apply_step_output(s1, {"v": 1}, state)
    s2 = _make_step(step_id="s2", output_mapping={"v": "vars.x"})
    _assert_raises(
        OutputMappingError,
        lambda: apply_step_output(s2, {"v": 2}, state),
        "overwrite still rejects duplicates",
    )

    # ── Invalid strategy ──
    state = create_execution_state("s1", {})
    s_bad = _make_step(
        output_mapping={"v": "vars.x"}, config={"merge_strategy": "invalid"}
    )
    _assert_raises(
        OutputMappingError,
        lambda: apply_step_output(s_bad, {"v": 1}, state),
        "invalid merge_strategy rejected",
    )


# ════════════════════════════════════════════════════════════════
# 7. Read-only enforcement
# ════════════════════════════════════════════════════════════════


def test_read_only_enforcement():
    print("▸ read-only enforcement")

    planner = ExecutionPlanner()

    # Planner rejects writes to frame
    _assert_raises(
        InvalidSkillSpecError,
        lambda: planner.build_plan(
            _make_skill(
                steps=[
                    _make_step(output_mapping={"v": "frame.goal"}),
                ]
            )
        ),
        "planner rejects frame writes",
    )

    # Planner rejects writes to inputs
    _assert_raises(
        InvalidSkillSpecError,
        lambda: planner.build_plan(
            _make_skill(
                steps=[
                    _make_step(output_mapping={"v": "inputs.text"}),
                ]
            )
        ),
        "planner rejects inputs writes",
    )

    # Planner rejects writes to trace
    _assert_raises(
        InvalidSkillSpecError,
        lambda: planner.build_plan(
            _make_skill(
                steps=[
                    _make_step(output_mapping={"v": "trace.steps"}),
                ]
            )
        ),
        "planner rejects trace writes",
    )

    # Planner accepts working, output, extensions
    skill = _make_skill(
        steps=[
            _make_step(step_id="s1", output_mapping={"a": "working.artifacts.x"}),
            _make_step(step_id="s2", output_mapping={"b": "output.summary"}),
            _make_step(step_id="s3", output_mapping={"c": "extensions.policy.ok"}),
        ]
    )
    plan = planner.build_plan(skill)
    _assert(len(plan) == 3, "planner accepts cognitive writable namespaces")


# ════════════════════════════════════════════════════════════════
# 8. Full pipeline with cognitive state
# ════════════════════════════════════════════════════════════════


def test_full_cognitive_pipeline():
    print("▸ full cognitive pipeline (frame + working + output)")

    resolver = ReferenceResolver()
    frame = FrameState(
        goal="Analyze risks in document",
        context={"domain": "finance"},
        constraints={"max_risks": 10},
    )
    state = create_execution_state(
        "analysis.risk", {"text": "Financial report Q3..."}, frame=frame
    )
    mark_started(state)

    # Step 1: Extract risks — reads from inputs + frame, writes to working.risks
    step1 = _make_step(
        step_id="extract",
        input_mapping={
            "text": "inputs.text",
            "goal": "frame.goal",
            "domain": "frame.context.domain",
        },
        output_mapping={"risks": "working.risks"},
        config={"merge_strategy": "append"},
    )
    step1_input = build_step_input(step1, state, resolver)
    _assert(step1_input["text"] == "Financial report Q3...", "step1 reads inputs.text")
    _assert(
        step1_input["goal"] == "Analyze risks in document", "step1 reads frame.goal"
    )
    _assert(step1_input["domain"] == "finance", "step1 reads frame.context.domain")

    step1_output = {
        "risks": [
            {"label": "currency exposure", "severity": "high"},
            {"label": "supply chain", "severity": "medium"},
        ]
    }
    apply_step_output(step1, step1_output, state)
    _assert(len(state.working.risks) == 2, "step1 wrote 2 risks")

    # Step 2: Score risks — reads working.risks, writes to working.artifacts
    step2 = _make_step(
        step_id="score",
        input_mapping={
            "items": "working.risks",
            "constraints": "frame.constraints",
        },
        output_mapping={"scored": "working.artifacts.scored_risks"},
    )
    step2_input = build_step_input(step2, state, resolver)
    _assert(len(step2_input["items"]) == 2, "step2 reads working.risks")
    _assert(
        step2_input["constraints"]["max_risks"] == 10, "step2 reads frame.constraints"
    )

    step2_output = {
        "scored": [
            {"label": "currency exposure", "score": 0.9},
            {"label": "supply chain", "score": 0.6},
        ]
    }
    apply_step_output(step2, step2_output, state)
    _assert(
        state.working.artifacts["scored_risks"][0]["score"] == 0.9,
        "step2 wrote scored_risks",
    )

    # Step 3: Synthesize — reads working, writes to outputs (legacy) + output (cognitive)
    step3 = _make_step(
        step_id="synthesize",
        input_mapping={
            "risks": "working.artifacts.scored_risks",
            "goal": "frame.goal",
        },
        output_mapping={
            "report": "outputs.result",
            "brief": "output.summary",
        },
    )
    step3_input = build_step_input(step3, state, resolver)
    _assert(step3_input["risks"][0]["score"] == 0.9, "step3 reads working.artifacts")
    _assert(
        step3_input["goal"] == "Analyze risks in document", "step3 reads frame.goal"
    )

    step3_output = {
        "report": {"title": "Risk Analysis", "items": state.working.risks},
        "brief": "2 risks identified, 1 high severity",
    }
    apply_step_output(step3, step3_output, state)
    _assert(
        state.outputs["result"]["title"] == "Risk Analysis",
        "step3 wrote legacy outputs",
    )
    _assert(
        state.output.summary == "2 risks identified, 1 high severity",
        "step3 wrote output.summary",
    )

    mark_finished(state, "completed")
    _assert(state.status == "completed", "pipeline completed")
    _assert(state.state_version == "1.0.0", "state_version present")


# ════════════════════════════════════════════════════════════════
# 9. Mixed legacy + cognitive
# ════════════════════════════════════════════════════════════════


def test_mixed_legacy_cognitive():
    print("▸ mixed legacy + cognitive mode")

    resolver = ReferenceResolver()
    state = create_execution_state("mixed.skill", {"doc": "content"})

    # Legacy step: vars + outputs
    step1 = _make_step(
        step_id="legacy",
        input_mapping={"text": "inputs.doc"},
        output_mapping={"chunk": "vars.extracted"},
    )
    apply_step_output(step1, {"chunk": "legacy chunk"}, state)
    _assert(state.vars["extracted"] == "legacy chunk", "legacy vars write works")

    # Cognitive step: reads vars, writes working
    step2 = _make_step(
        step_id="cognitive",
        input_mapping={"text": "vars.extracted"},
        output_mapping={"summary": "working.artifacts.summary"},
    )
    step2_input = build_step_input(step2, state, resolver)
    _assert(step2_input["text"] == "legacy chunk", "cognitive reads from legacy vars")
    apply_step_output(step2, {"summary": "cognitive summary"}, state)
    _assert(
        state.working.artifacts["summary"] == "cognitive summary",
        "cognitive write to working works",
    )

    # Another step reads from working
    step3 = _make_step(
        step_id="final",
        input_mapping={"s": "working.artifacts.summary"},
        output_mapping={"result": "outputs.result"},
    )
    step3_input = build_step_input(step3, state, resolver)
    _assert(step3_input["s"] == "cognitive summary", "cross-namespace read works")
    apply_step_output(step3, {"result": "done"}, state)
    _assert(state.outputs["result"] == "done", "final output to legacy works")


# ════════════════════════════════════════════════════════════════
# 10. Trace structures exist
# ════════════════════════════════════════════════════════════════


def test_trace_structures():
    print("▸ trace structures")

    state = create_execution_state("s1", {})

    _assert(isinstance(state.trace, TraceState), "trace is TraceState")
    _assert(
        isinstance(state.trace.metrics, TraceMetrics), "trace.metrics is TraceMetrics"
    )
    _assert(state.trace.steps == [], "trace.steps starts empty")
    _assert(state.trace.metrics.step_count == 0, "trace.metrics.step_count starts at 0")
    _assert(state.trace.metrics.elapsed_ms == 0, "trace.metrics.elapsed_ms starts at 0")

    # Manually append a TraceStep (simulating what engine does)
    ts = TraceStep(
        step_id="s1",
        capability_id="test.cap",
        status="completed",
        reads=("inputs.text", "frame.goal"),
        writes=("working.artifacts.summary",),
        latency_ms=42,
    )
    state.trace.steps.append(ts)
    state.trace.metrics.step_count += 1
    state.trace.metrics.elapsed_ms += 42

    _assert(len(state.trace.steps) == 1, "trace step appended")
    _assert(
        state.trace.steps[0].reads == ("inputs.text", "frame.goal"),
        "trace step reads correct",
    )
    _assert(
        state.trace.steps[0].writes == ("working.artifacts.summary",),
        "trace step writes correct",
    )
    _assert(state.trace.metrics.step_count == 1, "metrics step_count updated")
    _assert(state.trace.metrics.elapsed_ms == 42, "metrics elapsed_ms updated")


# ════════════════════════════════════════════════════════════════
# 11. Cognitive metadata
# ════════════════════════════════════════════════════════════════


def test_cognitive_metadata():
    print("▸ cognitive metadata")

    state = create_execution_state(
        "s1",
        {"text": "hello"},
        trace_id="t-1",
        skill_version="2.0.0",
        parent_run_id="parent-abc",
    )
    _assert(state.state_version == "1.0.0", "state_version is 1.0.0")
    _assert(state.skill_version == "2.0.0", "skill_version set")
    _assert(state.parent_run_id == "parent-abc", "parent_run_id set")
    _assert(state.iteration == 0, "iteration starts at 0")
    _assert(state.current_step is None, "current_step starts None")
    _assert(state.updated_at is not None, "updated_at set on creation")


# ════════════════════════════════════════════════════════════════
# 12. Path traversal edge cases
# ════════════════════════════════════════════════════════════════


def test_path_traversal_edge_cases():
    print("▸ path traversal edge cases")

    resolver = ReferenceResolver()

    # Tuple indexing (frame.assumptions)
    frame = FrameState(assumptions=("a1", "a2", "a3"))
    state = create_execution_state("s", {}, frame=frame)
    _assert(resolver.resolve("frame.assumptions.0", state) == "a1", "tuple index 0")
    _assert(resolver.resolve("frame.assumptions.2", state) == "a3", "tuple index 2")
    _assert(
        resolver.resolve("frame.assumptions.99", state) is None,
        "tuple out of range permissive",
    )

    # Deep nested dict in working.artifacts
    state2 = create_execution_state("s", {})
    step = _make_step(output_mapping={"v": "working.artifacts.deep.nested.value"})
    apply_step_output(step, {"v": 42}, state2)
    _assert(
        state2.working.artifacts["deep"]["nested"]["value"] == 42,
        "deep nested auto-create",
    )
    _assert(
        resolver.resolve("working.artifacts.deep.nested.value", state2) == 42,
        "resolve deep nested",
    )

    # Extensions nested
    state3 = create_execution_state("s", {})
    step2 = _make_step(output_mapping={"v": "extensions.memory.context.last_seen"})
    apply_step_output(step2, {"v": "2026-03-23"}, state3)
    _assert(
        state3.extensions["memory"]["context"]["last_seen"] == "2026-03-23",
        "extensions nested auto-create",
    )


# ════════════════════════════════════════════════════════════════
# 13. Deep merge strategy on working.artifacts
# ════════════════════════════════════════════════════════════════


def test_deep_merge_on_artifacts():
    print("▸ deep_merge on working.artifacts")

    state = create_execution_state("s1", {})

    # First write creates
    s1 = _make_step(
        step_id="s1",
        output_mapping={"data": "working.artifacts"},
        config={"merge_strategy": "deep_merge"},
    )
    apply_step_output(
        s1, {"data": {"analysis": {"score": 0.9}, "entities": ["e1"]}}, state
    )
    _assert(
        state.working.artifacts["analysis"]["score"] == 0.9, "deep_merge initial write"
    )

    # Second write merges
    s2 = _make_step(
        step_id="s2",
        output_mapping={"data": "working.artifacts"},
        config={"merge_strategy": "deep_merge"},
    )
    apply_step_output(
        s2, {"data": {"analysis": {"confidence": 0.8}, "summary": "ok"}}, state
    )
    _assert(
        state.working.artifacts["analysis"]["score"] == 0.9,
        "deep_merge preserves existing",
    )
    _assert(
        state.working.artifacts["analysis"]["confidence"] == 0.8,
        "deep_merge adds new nested key",
    )
    _assert(state.working.artifacts["summary"] == "ok", "deep_merge adds top-level key")


# ════════════════════════════════════════════════════════════════
# Runner
# ════════════════════════════════════════════════════════════════


def run_all():
    print("=" * 60)
    print("CognitiveState v1 — Integration Tests")
    print("=" * 60)
    print()

    test_frame_state()
    test_working_state()
    test_cognitive_slots()
    test_output_state()
    test_extensions()
    test_merge_strategies()
    test_read_only_enforcement()
    test_full_cognitive_pipeline()
    test_mixed_legacy_cognitive()
    test_trace_structures()
    test_cognitive_metadata()
    test_path_traversal_edge_cases()
    test_deep_merge_on_artifacts()

    print()
    print("=" * 60)
    print(f"Results: {_passed} passed, {_failed} failed")
    if _errors:
        print("Failures:")
        for err in _errors:
            print(f"  ✗ {err}")
    print("=" * 60)

    return _failed == 0


if __name__ == "__main__":
    import sys

    success = run_all()
    sys.exit(0 if success else 1)

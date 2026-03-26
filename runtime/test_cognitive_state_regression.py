"""
Regression tests for the execution pipeline BEFORE CognitiveState v1 upgrade.

These tests lock the current behavior of:
- create_execution_state
- ReferenceResolver
- build_step_input (InputMapper)
- apply_step_output (OutputMapper)
- ExecutionPlanner
- ExecutionEngine (integrated)

Run: python -m runtime.test_cognitive_state_regression
"""

from __future__ import annotations


from runtime.errors import (
    InputMappingError,
    InvalidSkillSpecError,
    OutputMappingError,
    ReferenceResolutionError,
)
from runtime.execution_planner import ExecutionPlanner
from runtime.execution_state import (
    create_execution_state,
    emit_event,
    get_step_result,
    has_written_target,
    mark_finished,
    mark_started,
    mark_target_written,
    record_step_result,
)
from runtime.input_mapper import build_step_input
from runtime.models import (
    ExecutionState,
    FieldSpec,
    SkillExecutionResult,
    SkillSpec,
    StepResult,
    StepSpec,
)
from runtime.output_mapper import apply_step_output
from runtime.reference_resolver import ReferenceResolver


# ════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════


def _make_step(
    step_id: str = "s1",
    uses: str = "text.content.summarize",
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
    inputs: dict[str, FieldSpec] | None = None,
    outputs: dict[str, FieldSpec] | None = None,
) -> SkillSpec:
    return SkillSpec(
        id=skill_id,
        version="1.0.0",
        name="Test Skill",
        description="A test skill",
        inputs=inputs or {"text": FieldSpec(type="string", required=True)},
        outputs=outputs or {"summary": FieldSpec(type="string", required=True)},
        steps=tuple(
            steps
            or [
                _make_step(
                    input_mapping={"text": "inputs.text"},
                    output_mapping={"summary": "outputs.summary"},
                )
            ]
        ),
        metadata={},
    )


def _make_state(
    skill_id: str = "test.skill",
    inputs: dict | None = None,
    vars_: dict | None = None,
    outputs: dict | None = None,
) -> ExecutionState:
    state = create_execution_state(skill_id, inputs or {"text": "hello"})
    if vars_:
        state.vars.update(vars_)
    if outputs:
        state.outputs.update(outputs)
    return state


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
        _errors.append(f"{msg} (wrong exception: {type(e).__name__}: {e})")
        print(f"  FAIL: {msg} (wrong exception: {type(e).__name__})")


# ════════════════════════════════════════════════════════════════
# 1. create_execution_state
# ════════════════════════════════════════════════════════════════


def test_create_execution_state():
    print("▸ create_execution_state")

    state = create_execution_state("my.skill", {"a": 1, "b": "two"}, trace_id="t-1")

    _assert(state.skill_id == "my.skill", "skill_id preserved")
    _assert(state.inputs == {"a": 1, "b": "two"}, "inputs preserved")
    _assert(state.vars == {}, "vars starts empty")
    _assert(state.outputs == {}, "outputs starts empty")
    _assert(state.step_results == {}, "step_results starts empty")
    _assert(state.written_targets == set(), "written_targets starts empty")
    _assert(state.events == [], "events starts empty")
    _assert(state.status == "pending", "status starts pending")
    _assert(state.trace_id == "t-1", "trace_id preserved")
    _assert(state.started_at is not None, "started_at set")
    _assert(state.finished_at is None, "finished_at is None")

    # inputs should be a copy
    original = {"x": 1}
    state2 = create_execution_state("s", original)
    original["x"] = 999
    _assert(state2.inputs["x"] == 1, "inputs are copied, not referenced")


# ════════════════════════════════════════════════════════════════
# 2. State mutation helpers
# ════════════════════════════════════════════════════════════════


def test_state_helpers():
    print("▸ state mutation helpers")

    state = _make_state()

    # mark_started
    mark_started(state)
    _assert(state.status == "running", "mark_started sets running")
    _assert(state.started_at is not None, "mark_started sets started_at")

    # emit_event
    evt = emit_event(state, "test_event", "hello", step_id="s1", data={"k": "v"})
    _assert(len(state.events) == 1, "event appended")
    _assert(evt.type == "test_event", "event type correct")
    _assert(evt.message == "hello", "event message correct")
    _assert(evt.step_id == "s1", "event step_id correct")
    _assert(evt.data == {"k": "v"}, "event data correct")

    # record_step_result
    sr = StepResult(
        step_id="s1",
        uses="cap.a",
        status="completed",
        resolved_input={},
        produced_output={"x": 1},
    )
    record_step_result(state, sr)
    _assert(get_step_result(state, "s1") is sr, "step result recorded")
    _assert(get_step_result(state, "s999") is None, "missing step result returns None")

    # written targets
    _assert(not has_written_target(state, "vars.x"), "target not written yet")
    mark_target_written(state, "vars.x")
    _assert(has_written_target(state, "vars.x"), "target marked as written")

    # mark_finished
    mark_finished(state, "completed")
    _assert(state.status == "completed", "mark_finished sets status")
    _assert(state.finished_at is not None, "mark_finished sets finished_at")


# ════════════════════════════════════════════════════════════════
# 3. ReferenceResolver
# ════════════════════════════════════════════════════════════════


def test_reference_resolver():
    print("▸ ReferenceResolver")

    resolver = ReferenceResolver()
    state = _make_state(
        inputs={"text": "hello", "count": 3},
        vars_={"chunk": "piece"},
        outputs={"result": "done"},
    )

    # Literals pass through
    _assert(resolver.resolve(42, state) == 42, "int literal passes through")
    _assert(resolver.resolve(True, state) is True, "bool literal passes through")
    _assert(resolver.resolve(None, state) is None, "None passes through")
    _assert(resolver.resolve("plain", state) == "plain", "no-dot string passes through")
    _assert(
        resolver.resolve("a sentence with dots.", state) == "a sentence with dots.",
        "non-namespace dotted string passes through",
    )

    # inputs namespace
    _assert(resolver.resolve("inputs.text", state) == "hello", "inputs.text resolved")
    _assert(resolver.resolve("inputs.count", state) == 3, "inputs.count resolved")
    _assert(
        resolver.resolve("inputs.missing", state) is None,
        "inputs.missing returns None (optional)",
    )

    # vars namespace
    _assert(resolver.resolve("vars.chunk", state) == "piece", "vars.chunk resolved")
    _assert_raises(
        ReferenceResolutionError,
        lambda: resolver.resolve("vars.nope", state),
        "vars.nope raises error",
    )

    # outputs namespace
    _assert(
        resolver.resolve("outputs.result", state) == "done", "outputs.result resolved"
    )
    _assert_raises(
        ReferenceResolutionError,
        lambda: resolver.resolve("outputs.nope", state),
        "outputs.nope raises error",
    )

    # Unknown namespace treated as literal
    _assert(
        resolver.resolve("unknown.field", state) == "unknown.field",
        "unknown namespace is literal",
    )
    _assert(
        resolver.resolve("frame.goal", state) is None,
        "frame.goal resolves to None (no goal set)",
    )


# ════════════════════════════════════════════════════════════════
# 4. build_step_input (InputMapper)
# ════════════════════════════════════════════════════════════════


def test_build_step_input():
    print("▸ build_step_input")

    resolver = ReferenceResolver()
    state = _make_state(
        inputs={"text": "hello", "lang": "es"}, vars_={"chunk": "piece"}
    )

    # Simple mapping
    step = _make_step(input_mapping={"text": "inputs.text", "language": "inputs.lang"})
    result = build_step_input(step, state, resolver)
    _assert(result == {"text": "hello", "language": "es"}, "simple mapping resolved")

    # Literal values
    step = _make_step(input_mapping={"mode": "fast", "count": 5})
    result = build_step_input(step, state, resolver)
    _assert(result == {"mode": "fast", "count": 5}, "literals preserved")

    # Nested dict
    step = _make_step(input_mapping={"config": {"text": "inputs.text", "mode": "fast"}})
    result = build_step_input(step, state, resolver)
    _assert(
        result == {"config": {"text": "hello", "mode": "fast"}}, "nested dict resolved"
    )

    # List values
    step = _make_step(input_mapping={"items": ["inputs.text", "inputs.lang"]})
    result = build_step_input(step, state, resolver)
    _assert(result == {"items": ["hello", "es"]}, "list values resolved")

    # Mixed vars + inputs
    step = _make_step(input_mapping={"text": "vars.chunk", "original": "inputs.text"})
    result = build_step_input(step, state, resolver)
    _assert(result == {"text": "piece", "original": "hello"}, "mixed sources resolved")

    # Error on missing var
    step = _make_step(input_mapping={"text": "vars.nonexistent"})
    _assert_raises(
        InputMappingError,
        lambda: build_step_input(step, state, resolver),
        "missing var raises InputMappingError",
    )


# ════════════════════════════════════════════════════════════════
# 5. apply_step_output (OutputMapper)
# ════════════════════════════════════════════════════════════════


def test_apply_step_output():
    print("▸ apply_step_output")

    # Write to vars
    state = _make_state()
    step = _make_step(output_mapping={"summary": "vars.chunk"})
    apply_step_output(step, {"summary": "a summary"}, state)
    _assert(state.vars["chunk"] == "a summary", "write to vars works")
    _assert(has_written_target(state, "vars.chunk"), "vars.chunk marked as written")

    # Write to outputs
    state = _make_state()
    step = _make_step(output_mapping={"summary": "outputs.result"})
    apply_step_output(step, {"summary": "final"}, state)
    _assert(state.outputs["result"] == "final", "write to outputs works")

    # Multiple mappings in one step
    state = _make_state()
    step = _make_step(output_mapping={"a": "vars.x", "b": "outputs.y"})
    apply_step_output(step, {"a": 1, "b": 2}, state)
    _assert(state.vars["x"] == 1 and state.outputs["y"] == 2, "multiple mappings work")

    # Duplicate write error
    state = _make_state()
    step1 = _make_step(step_id="s1", output_mapping={"v": "vars.x"})
    step2 = _make_step(step_id="s2", output_mapping={"v": "vars.x"})
    apply_step_output(step1, {"v": 1}, state)
    _assert_raises(
        OutputMappingError,
        lambda: apply_step_output(step2, {"v": 2}, state),
        "duplicate write raises OutputMappingError",
    )

    # Cannot write to inputs
    state = _make_state()
    step = _make_step(output_mapping={"v": "inputs.text"})
    _assert_raises(
        OutputMappingError,
        lambda: apply_step_output(step, {"v": "x"}, state),
        "write to inputs raises OutputMappingError",
    )

    # Cannot write to unknown namespace
    state = _make_state()
    step = _make_step(output_mapping={"v": "unknown.x"})
    _assert_raises(
        OutputMappingError,
        lambda: apply_step_output(step, {"v": "x"}, state),
        "write to truly unknown namespace raises OutputMappingError",
    )

    # Non-dict step output
    state = _make_state()
    step = _make_step(output_mapping={"v": "vars.x"})
    _assert_raises(
        OutputMappingError,
        lambda: apply_step_output(step, "not a dict", state),
        "non-dict step output raises OutputMappingError",
    )

    # Nested produced path
    state = _make_state()
    step = _make_step(output_mapping={"result.text": "vars.extracted"})
    apply_step_output(step, {"result": {"text": "nested value"}}, state)
    _assert(state.vars["extracted"] == "nested value", "nested produced path resolved")

    # State-referencing produced path (vars.*)
    state = _make_state(vars_={"existing": "from_vars"})
    step = _make_step(output_mapping={"vars.existing": "outputs.copied"})
    apply_step_output(step, {}, state)
    _assert(
        state.outputs["copied"] == "from_vars", "vars.* produced path reads from state"
    )


# ════════════════════════════════════════════════════════════════
# 6. ExecutionPlanner
# ════════════════════════════════════════════════════════════════


def test_execution_planner():
    print("▸ ExecutionPlanner")

    planner = ExecutionPlanner()

    # Valid skill passes
    skill = _make_skill()
    plan = planner.build_plan(skill)
    _assert(len(plan) == 1, "valid skill returns 1 step")

    # No steps
    empty_skill = SkillSpec(
        id="empty",
        version="1.0.0",
        name="Empty",
        description="",
        inputs={},
        outputs={},
        steps=(),
        metadata={},
    )
    _assert_raises(
        InvalidSkillSpecError,
        lambda: planner.build_plan(empty_skill),
        "no steps raises error",
    )

    # Duplicate step ids
    _assert_raises(
        InvalidSkillSpecError,
        lambda: planner.build_plan(
            _make_skill(
                steps=[
                    _make_step(step_id="same", output_mapping={"a": "vars.a"}),
                    _make_step(step_id="same", output_mapping={"b": "vars.b"}),
                ]
            )
        ),
        "duplicate step ids raises error",
    )

    # Valid namespaces: vars and outputs
    skill = _make_skill(
        steps=[
            _make_step(step_id="s1", output_mapping={"a": "vars.x"}),
            _make_step(step_id="s2", output_mapping={"b": "outputs.summary"}),
        ]
    )
    plan = planner.build_plan(skill)
    _assert(len(plan) == 2, "vars and outputs namespaces accepted")

    # Invalid namespace
    _assert_raises(
        InvalidSkillSpecError,
        lambda: planner.build_plan(
            _make_skill(
                steps=[
                    _make_step(output_mapping={"a": "unknown.x"}),
                ]
            )
        ),
        "unknown namespace rejected",
    )

    _assert_raises(
        InvalidSkillSpecError,
        lambda: planner.build_plan(
            _make_skill(
                steps=[
                    _make_step(output_mapping={"a": "frame.goal"}),
                ]
            )
        ),
        "frame namespace rejected (read-only)",
    )

    _assert_raises(
        InvalidSkillSpecError,
        lambda: planner.build_plan(
            _make_skill(
                steps=[
                    _make_step(output_mapping={"a": "inputs.text"}),
                ]
            )
        ),
        "inputs namespace rejected (read-only)",
    )

    # No dot in target
    _assert_raises(
        InvalidSkillSpecError,
        lambda: planner.build_plan(
            _make_skill(
                steps=[
                    _make_step(output_mapping={"a": "nodot"}),
                ]
            )
        ),
        "target without dot rejected",
    )


# ════════════════════════════════════════════════════════════════
# 7. Integrated execution (mini end-to-end)
# ════════════════════════════════════════════════════════════════


def test_integrated_execution():
    """
    Simulates the engine flow without the full ExecutionEngine to avoid
    depending on loaders/binding — tests the state pipeline end-to-end.
    """
    print("▸ integrated execution pipeline")

    resolver = ReferenceResolver()
    planner = ExecutionPlanner()

    # Skill: two steps, step1 writes to vars, step2 reads vars and writes to outputs
    skill = _make_skill(
        inputs={"text": FieldSpec(type="string", required=True)},
        outputs={"summary": FieldSpec(type="string", required=True)},
        steps=[
            _make_step(
                step_id="extract",
                input_mapping={"text": "inputs.text"},
                output_mapping={"chunk": "vars.extracted"},
            ),
            _make_step(
                step_id="summarize",
                input_mapping={"text": "vars.extracted"},
                output_mapping={"summary": "outputs.summary"},
            ),
        ],
    )

    # 1. Create state
    state = create_execution_state(skill.id, {"text": "long document content"})
    _assert(state.status == "pending", "initial status pending")

    # 2. Mark started
    mark_started(state)
    _assert(state.status == "running", "status running after mark_started")

    # 3. Plan
    plan = planner.build_plan(skill)
    _assert(len(plan) == 2, "plan has 2 steps")

    # 4. Execute step 1
    step1_input = build_step_input(plan[0], state, resolver)
    _assert(
        step1_input == {"text": "long document content"},
        "step1 input resolved from inputs",
    )

    # Simulate capability producing output
    step1_output = {"chunk": "extracted chunk"}
    apply_step_output(plan[0], step1_output, state)
    _assert(state.vars["extracted"] == "extracted chunk", "step1 wrote to vars")

    emit_event(state, "step_completed", "Step extract completed", step_id="extract")

    # 5. Execute step 2
    step2_input = build_step_input(plan[1], state, resolver)
    _assert(
        step2_input == {"text": "extracted chunk"}, "step2 input resolved from vars"
    )

    step2_output = {"summary": "This is a summary"}
    apply_step_output(plan[1], step2_output, state)
    _assert(state.outputs["summary"] == "This is a summary", "step2 wrote to outputs")

    emit_event(state, "step_completed", "Step summarize completed", step_id="summarize")

    # 6. Finalize
    mark_finished(state, "completed")
    _assert(state.status == "completed", "final status completed")
    _assert(state.finished_at is not None, "finished_at set")
    _assert(len(state.events) == 2, "2 events emitted")

    # 7. Build result
    result = SkillExecutionResult(
        skill_id=skill.id,
        status=state.status,
        outputs=dict(state.outputs),
        state=state,
    )
    _assert(result.outputs == {"summary": "This is a summary"}, "final outputs correct")
    _assert(result.status == "completed", "result status correct")


# ════════════════════════════════════════════════════════════════
# 8. Multi-step composition with vars chaining
# ════════════════════════════════════════════════════════════════


def test_multi_step_composition():
    """Test a 3-step pipeline with chained vars."""
    print("▸ multi-step composition")

    resolver = ReferenceResolver()
    state = _make_state(inputs={"doc": "raw content"})
    mark_started(state)

    steps = [
        _make_step(
            step_id="chunk",
            input_mapping={"text": "inputs.doc"},
            output_mapping={"chunks": "vars.chunks"},
        ),
        _make_step(
            step_id="analyze",
            input_mapping={"data": "vars.chunks"},
            output_mapping={"analysis": "vars.analysis"},
        ),
        _make_step(
            step_id="report",
            input_mapping={"analysis": "vars.analysis", "original": "inputs.doc"},
            output_mapping={"report": "outputs.report"},
        ),
    ]

    simulated_outputs = [
        {"chunks": ["c1", "c2", "c3"]},
        {"analysis": {"score": 0.9, "theme": "tech"}},
        {"report": "Final report based on analysis"},
    ]

    for step, sim_output in zip(steps, simulated_outputs):
        step_input = build_step_input(step, state, resolver)
        apply_step_output(step, sim_output, state)
        record_step_result(
            state,
            StepResult(
                step_id=step.id,
                uses=step.uses,
                status="completed",
                resolved_input=step_input,
                produced_output=sim_output,
            ),
        )

    mark_finished(state, "completed")

    _assert(state.vars["chunks"] == ["c1", "c2", "c3"], "chunks in vars")
    _assert(state.vars["analysis"]["score"] == 0.9, "analysis in vars")
    _assert(
        state.outputs["report"] == "Final report based on analysis", "report in outputs"
    )
    _assert(len(state.step_results) == 3, "all 3 step results recorded")
    _assert(state.status == "completed", "final status completed")


# ════════════════════════════════════════════════════════════════
# 9. Edge cases
# ════════════════════════════════════════════════════════════════


def test_edge_cases():
    print("▸ edge cases")

    resolver = ReferenceResolver()

    # Empty input mapping
    state = _make_state()
    step = _make_step(input_mapping={})
    result = build_step_input(step, state, resolver)
    _assert(result == {}, "empty input mapping returns empty dict")

    # Empty output mapping — no writes
    state = _make_state()
    step = _make_step(output_mapping={})
    apply_step_output(step, {"anything": "ignored"}, state)
    _assert(
        state.vars == {} and state.outputs == {}, "empty output mapping writes nothing"
    )

    # Complex nested input
    state = _make_state(inputs={"text": "hello"})
    step = _make_step(
        input_mapping={
            "config": {
                "items": ["inputs.text", "literal"],
                "nested": {"deep": "inputs.text"},
            }
        }
    )
    result = build_step_input(step, state, resolver)
    _assert(
        result["config"]["items"] == ["hello", "literal"],
        "nested list in dict resolved",
    )
    _assert(result["config"]["nested"]["deep"] == "hello", "deep nested resolved")

    # Produced output with list index
    state = _make_state()
    step = _make_step(output_mapping={"items.0.id": "vars.first_id"})
    apply_step_output(step, {"items": [{"id": "abc"}, {"id": "def"}]}, state)
    _assert(state.vars["first_id"] == "abc", "list index in produced path works")

    # resolve_mapping helper
    state = _make_state(inputs={"a": 1, "b": 2})
    resolved = resolver.resolve_mapping(
        {"x": "inputs.a", "y": "inputs.b", "z": "literal"}, state
    )
    _assert(resolved == {"x": 1, "y": 2, "z": "literal"}, "resolve_mapping works")


# ════════════════════════════════════════════════════════════════
# Runner
# ════════════════════════════════════════════════════════════════


def run_all():
    print("=" * 60)
    print("CognitiveState v1 — Pre-upgrade Regression Tests")
    print("=" * 60)
    print()

    test_create_execution_state()
    test_state_helpers()
    test_reference_resolver()
    test_build_step_input()
    test_apply_step_output()
    test_execution_planner()
    test_integrated_execution()
    test_multi_step_composition()
    test_edge_cases()

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

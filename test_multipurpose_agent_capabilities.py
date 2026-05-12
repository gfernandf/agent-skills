#!/usr/bin/env python3
"""
Test suite for the 18 multipurpose agent pipeline capabilities.

Tests each capability's Python fallback binding by:
  1. Importing the baseline service function directly
  2. Calling it with minimal valid inputs
  3. Asserting required output fields are present
  4. Asserting basic type constraints

No API key is required — all tests use the pythoncall / baseline path.

Usage:
  python test_multipurpose_agent_capabilities.py
  python test_multipurpose_agent_capabilities.py agent.request.normalize ops.trace.summarize
"""

import importlib
import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PASS = "PASS"
FAIL = "FAIL"


def assert_keys(result, *keys, context=""):
    for key in keys:
        if key not in result:
            raise AssertionError(
                f"Missing key '{key}' in result{' (' + context + ')' if context else ''}. "
                f"Got keys: {sorted(result.keys())}"
            )


def run_test(name, fn):
    print(f"\n{'=' * 70}")
    print(f"  CAPABILITY: {name}")
    print(f"{'=' * 70}")
    try:
        fn()
        print(f"  STATUS     : {PASS}")
        return True
    except AssertionError as exc:
        print(f"  STATUS     : {FAIL}")
        print(f"  ASSERTION  : {exc}")
        return False
    except Exception as exc:
        print(f"  STATUS     : {FAIL}")
        print(f"  EXCEPTION  : {exc}")
        traceback.print_exc()
        return False


# ---------------------------------------------------------------------------
# Import baseline modules
# ---------------------------------------------------------------------------

try:
    import official_services.agent_baseline as agent_bl
except ImportError:
    from agent_skills.official_services import agent_baseline as agent_bl  # type: ignore  # noqa: F401

try:
    import official_services.eval_baseline as eval_bl
except ImportError:
    from agent_skills.official_services import eval_baseline as eval_bl  # type: ignore  # noqa: F401

try:
    import official_services.ops_baseline as ops_bl
except ImportError:
    from agent_skills.official_services import ops_baseline as ops_bl  # type: ignore  # noqa: F401

# ---------------------------------------------------------------------------
# Individual capability tests
# ---------------------------------------------------------------------------


def test_agent_request_normalize():
    result = agent_bl.normalize_request(
        user_message="Create a summary report of the Q4 sales data",
        context={"session_id": "test-001"},
    )
    assert_keys(result, "normalized_request", "language")
    nr = result["normalized_request"]
    assert_keys(nr, "raw_request", "language", "detected_intent",
                "explicit_constraints", "urgency", "requires_external_action",
                "attachments", context="normalized_request")
    assert nr["urgency"] in ("low", "medium", "high"), f"Invalid urgency: {nr['urgency']}"
    assert isinstance(nr["explicit_constraints"], list)
    assert isinstance(nr["attachments"], list)


def test_agent_goal_interpret():
    nr = {
        "raw_request": "Summarize Q4 sales data",
        "language": "en",
        "detected_intent": "summarize",
        "explicit_constraints": [],
        "urgency": "medium",
        "requires_external_action": False,
        "attachments": [],
    }
    result = agent_bl.interpret_goal(normalized_request=nr)
    assert_keys(result, "interpreted_goal", "requires_clarification")
    goal = result["interpreted_goal"]
    assert_keys(goal, "objective", "deliverable_type", "success_criteria",
                "constraints", "assumptions", "open_questions",
                context="interpreted_goal")
    assert isinstance(goal["success_criteria"], list)
    assert isinstance(result["requires_clarification"], bool)


def test_agent_criteria_define():
    goal = {
        "objective": "Produce Q4 sales summary",
        "deliverable_type": "report",
        "success_criteria": ["Report covers all regions"],
        "constraints": [],
        "assumptions": [],
        "open_questions": [],
    }
    result = agent_bl.define_criteria(interpreted_goal=goal)
    assert_keys(result, "success_criteria", "quality_criteria", "acceptance_criteria")
    for key in ("success_criteria", "quality_criteria", "acceptance_criteria"):
        assert isinstance(result[key], list), f"{key} must be a list"


def test_agent_catalog_search():
    goal = {"objective": "search for relevant skills", "deliverable_type": "task_output"}
    result = agent_bl.search_catalog(goal=goal)
    assert_keys(result, "candidate_items", "total_matched")
    assert isinstance(result["candidate_items"], list)
    assert isinstance(result["total_matched"], int)
    for item in result["candidate_items"]:
        assert_keys(item, "ref", "type", "relevance_score", "reason",
                    context="candidate_item")
        assert 0.0 <= item["relevance_score"] <= 1.0


def test_agent_catalog_rank():
    candidates = [
        {"ref": "web.source.search", "type": "capability", "relevance_score": 0.8, "reason": "A"},
        {"ref": "agent.plan-and-route", "type": "skill", "relevance_score": 0.6, "reason": "B"},
    ]
    goal = {"objective": "rank test"}
    result = agent_bl.rank_catalog(candidate_items=candidates, interpreted_goal=goal)
    assert_keys(result, "ranked_skills", "ranked_capabilities")
    for item in result["ranked_capabilities"]:
        assert_keys(item, "rank", "ref", "relevance_score", context="ranked_capability")
    for item in result["ranked_skills"]:
        assert_keys(item, "rank", "ref", context="ranked_skill")


def test_agent_catalog_detect():
    goal = {"objective": "detect gaps"}
    candidates = [{"ref": "web.source.search", "type": "capability", "relevance_score": 0.7}]
    result = agent_bl.detect_catalog_gaps(interpreted_goal=goal, candidate_items=candidates)
    assert_keys(result, "missing_capabilities", "missing_skills", "gap_severity")
    assert result["gap_severity"] in ("none", "minor", "blocking")


def test_agent_task_plan():
    goal = {"objective": "create macro plan", "deliverable_type": "plan"}
    result = agent_bl.create_macro_plan(interpreted_goal=goal)
    assert_keys(result, "macro_plan", "stage_count")
    plan = result["macro_plan"]
    assert_keys(plan, "goal_ref", "strategy", "stages", context="macro_plan")
    assert isinstance(plan["stages"], list)
    assert result["stage_count"] == len(plan["stages"])


def test_agent_plan_split():
    stage = {"id": "s1", "objective": "Gather data"}
    result = agent_bl.split_plan_stage(macro_stage=stage)
    assert_keys(result, "expanded_steps", "step_count")
    assert isinstance(result["expanded_steps"], list)
    assert result["step_count"] == len(result["expanded_steps"])
    for step in result["expanded_steps"]:
        assert_keys(step, "id", "type", "ref", "purpose", "inputs", "outputs", "depends_on",
                    context="expanded_step")


def test_agent_plan_map():
    steps = [
        {
            "id": "s1_step1",
            "type": "capability",
            "ref": "web.source.search",
            "purpose": "Search",
            "inputs": {"query": "search"},
            "outputs": {"results": "data"},
            "depends_on": [],
        }
    ]
    result = agent_bl.map_plan_inputs(expanded_steps=steps)
    assert_keys(result, "bound_steps", "unresolved_bindings")
    assert isinstance(result["bound_steps"], list)
    assert isinstance(result["unresolved_bindings"], list)
    if result["bound_steps"]:
        step = result["bound_steps"][0]
        assert_keys(step, "id", "inputs", "outputs", context="bound_step")
        # Verify $state. binding paths were applied
        for v in step["inputs"].values():
            assert v.startswith("$state."), f"Expected $state.* path, got: {v}"


def test_agent_plan_validate():
    plan = {
        "bound_steps": [
            {
                "id": "step_1",
                "type": "capability",
                "ref": "web.source.search",
                "inputs": {},
                "outputs": {},
                "depends_on": [],
            },
            {
                "id": "step_2",
                "type": "capability",
                "ref": "text.content.summarize",
                "inputs": {},
                "outputs": {},
                "depends_on": ["step_1"],
            },
        ]
    }
    result = agent_bl.validate_plan(expanded_plan=plan)
    assert_keys(result, "validation_result")
    vr = result["validation_result"]
    assert_keys(vr, "status", "errors", "warnings", "repairable", "check_count",
                context="validation_result")
    assert vr["status"] in ("passed", "failed")
    assert isinstance(vr["errors"], list)
    # Plan above is valid, expect passed
    assert vr["status"] == "passed", f"Expected passed, got {vr['status']}: {vr['errors']}"


def test_agent_plan_validate_detects_bad_deps():
    plan = {
        "bound_steps": [
            {
                "id": "step_1",
                "type": "capability",
                "ref": "web.source.search",
                "inputs": {},
                "outputs": {},
                "depends_on": ["nonexistent_step"],
            }
        ]
    }
    result = agent_bl.validate_plan(expanded_plan=plan)
    vr = result["validation_result"]
    assert vr["status"] == "failed"
    assert any(e.get("check") == "deps_exist" for e in vr["errors"])


def test_agent_plan_reconcile():
    invalid_plan = {
        "bound_steps": [
            {
                "id": "step_1",
                "type": "capability",
                "ref": "web.source.search",
                "inputs": {},
                "outputs": {},
                "depends_on": ["ghost_step"],
            }
        ]
    }
    errors = [{"step_id": "step_1", "check": "deps_exist",
               "message": "depends_on references unknown step 'ghost_step'"}]
    result = agent_bl.reconcile_plan(
        invalid_plan=invalid_plan, validation_errors=errors
    )
    assert_keys(result, "repaired_plan", "repair_notes", "still_invalid")
    assert isinstance(result["repair_notes"], list)
    assert isinstance(result["still_invalid"], bool)
    # Verify the bad dependency was removed
    steps = result["repaired_plan"].get("bound_steps", [])
    for step in steps:
        assert "ghost_step" not in step.get("depends_on", [])


def test_agent_plan_synthesize():
    plan = {
        "bound_steps": [
            {"id": "step_1", "type": "capability", "ref": "web.source.search",
             "inputs": {}, "outputs": {}, "depends_on": []},
            {"id": "step_2", "type": "capability", "ref": "text.content.summarize",
             "inputs": {}, "outputs": {}, "depends_on": ["step_1"]},
        ]
    }
    result = agent_bl.synthesize_plan(validated_plan=plan)
    assert_keys(result, "compiled_plan", "step_count")
    cp = result["compiled_plan"]
    assert_keys(cp, "dag", "execution_order", "parallel_groups", "gates",
                "state_bindings", "registry_version", "plan_hash",
                context="compiled_plan")
    assert isinstance(cp["execution_order"], list)
    assert result["step_count"] == len(cp["execution_order"])
    assert len(cp["plan_hash"]) == 16


def test_agent_plan_gate():
    compiled_plan = {
        "dag": {
            "nodes": [
                {"id": "step_1", "ref": "web.source.search", "type": "capability"},
            ],
            "edges": [],
        },
        "execution_order": ["step_1"],
        "parallel_groups": [["step_1"]],
        "gates": [],
        "state_bindings": {},
        "registry_version": "current",
        "plan_hash": "abc123",
    }
    result = agent_bl.gate_plan(compiled_plan=compiled_plan)
    assert_keys(result, "authorization_result")
    ar = result["authorization_result"]
    assert_keys(ar, "status", "blocked_steps", "approval_prompts", "risk_level",
                context="authorization_result")
    assert ar["status"] in ("approved", "denied", "requires_user_approval")
    assert isinstance(ar["blocked_steps"], list)


def test_agent_plan_execute():
    compiled_plan = {
        "dag": {
            "nodes": [
                {"id": "step_1", "ref": "web.source.search", "type": "capability"},
                {"id": "step_2", "ref": "text.content.summarize", "type": "capability"},
            ],
            "edges": [{"from": "step_1", "to": "step_2"}],
        },
        "execution_order": ["step_1", "step_2"],
        "parallel_groups": [["step_1"]],
        "gates": [],
        "state_bindings": {},
        "registry_version": "current",
        "plan_hash": "abc456",
    }
    result = agent_bl.execute_plan(compiled_plan=compiled_plan, initial_state={})
    assert_keys(result, "execution_result", "failed_steps")
    er = result["execution_result"]
    assert_keys(er, "status", "final_state", "step_results", "total_duration_ms",
                context="execution_result")
    assert er["status"] in ("success", "partial", "failed")
    assert isinstance(er["step_results"], list)
    assert isinstance(result["failed_steps"], list)


def test_agent_output_generate():
    goal = {"objective": "Test the pipeline", "deliverable_type": "report"}
    exec_result = {
        "status": "success",
        "final_state": {},
        "step_results": [
            {"step_id": "s1", "ref": "web.source.search", "status": "success",
             "outputs": {}, "error": None, "duration_ms": 200}
        ],
        "total_duration_ms": 200,
    }
    evaluation = {
        "evaluation": {
            "passed": True,
            "score": 0.9,
            "criteria_results": [],
            "failed_criteria": [],
            "improvement_suggestions": [],
        }
    }
    result = agent_bl.generate_output_report(
        interpreted_goal=goal,
        execution_result=exec_result,
        evaluation=evaluation,
    )
    assert_keys(result, "report", "report_status")
    report = result["report"]
    assert_keys(report, "user_response", "artifacts", "limitations",
                "next_steps", "evidence", context="report")
    assert isinstance(report["user_response"], str)
    assert result["report_status"] in ("success", "partial", "failed", "requires_followup")


def test_agent_output_synthesize():
    compiled_plan = {
        "dag": {
            "nodes": [
                {"id": "step_1", "ref": "web.source.search", "type": "capability"},
            ],
            "edges": [],
        },
        "execution_order": ["step_1"],
        "parallel_groups": [["step_1"]],
        "gates": [],
        "state_bindings": {},
        "registry_version": "current",
        "plan_hash": "abc789",
    }
    execution_trace = {
        "status": "success",
        "step_results": [
            {"step_id": "step_1", "ref": "web.source.search", "status": "success",
             "outputs": {}, "error": None, "duration_ms": 200}
        ],
        "total_duration_ms": 200,
        "final_state": {},
    }
    result = agent_bl.synthesize_output_skill(
        successful_plan=compiled_plan, execution_trace=execution_trace
    )
    assert_keys(result, "candidate_skill", "confidence")
    cs = result["candidate_skill"]
    assert_keys(cs, "name", "description", "version", "steps",
                "inputs", "outputs", "tags", "notes",
                context="candidate_skill")
    assert cs["version"] == "0.1.0"
    assert 0.0 <= result["confidence"] <= 1.0


def test_eval_output_validate():
    result = eval_bl.validate_output(
        final_output={"summary": "Q4 sales were strong", "total": 1_200_000},
        success_criteria=[
            "The output includes a summary",
            "The output includes a numeric total",
        ],
        evidence=None,
    )
    assert_keys(result, "evaluation")
    ev = result["evaluation"]
    assert_keys(ev, "passed", "score", "criteria_results",
                "failed_criteria", "improvement_suggestions",
                context="evaluation")
    assert isinstance(ev["passed"], bool)
    assert 0.0 <= ev["score"] <= 1.0
    assert len(ev["criteria_results"]) == 2
    for cr in ev["criteria_results"]:
        assert_keys(cr, "criterion", "met", "score", "rationale",
                    context="criterion_result")


def test_ops_trace_summarize():
    trace = {
        "status": "success",
        "step_results": [
            {"step_id": "s1", "ref": "web.source.search", "status": "success",
             "outputs": {}, "error": None, "duration_ms": 150},
            {"step_id": "s2", "ref": "text.content.summarize", "status": "success",
             "outputs": {}, "error": None, "duration_ms": 200},
        ],
        "total_duration_ms": 350,
        "final_state": {},
    }
    result = ops_bl.summarize_trace(execution_trace=trace)
    assert_keys(result, "trace_summary")
    ts = result["trace_summary"]
    assert_keys(ts, "steps_executed", "decisions", "failures",
                "overall_status", "total_duration_ms", "success_rate",
                context="trace_summary")
    assert len(ts["steps_executed"]) == 2
    assert ts["overall_status"] == "success"
    assert ts["total_duration_ms"] == 350
    assert ts["success_rate"] == 1.0
    assert isinstance(ts["failures"], list)
    assert len(ts["failures"]) == 0


# ---------------------------------------------------------------------------
# Registry / binding file validation helpers
# ---------------------------------------------------------------------------


def test_binding_files_exist():
    """All 18 capabilities must have both bindings files present."""
    bindings_root = Path(__file__).parent / "bindings" / "official"
    expected = [
        "agent.request.normalize",
        "agent.goal.interpret",
        "agent.criteria.define",
        "agent.catalog.search",
        "agent.catalog.rank",
        "agent.catalog.detect",
        "agent.task.plan",
        "agent.plan.split",
        "agent.plan.map",
        "agent.plan.validate",
        "agent.plan.reconcile",
        "agent.plan.synthesize",
        "agent.plan.gate",
        "agent.plan.run",
        "agent.output.generate",
        "agent.output.synthesize",
        "eval.output.validate",
        "ops.trace.summarize",
    ]
    missing = []
    for cap_id in expected:
        cap_dir = bindings_root / cap_id
        if not cap_dir.is_dir():
            missing.append(f"{cap_id}/ (directory missing)")
            continue
        yaml_files = list(cap_dir.glob("*.yaml"))
        if len(yaml_files) < 2:
            missing.append(
                f"{cap_id}/ (has {len(yaml_files)} yaml files, expected 2)"
            )
    if missing:
        raise AssertionError("Missing binding files:\n" + "\n".join(f"  - {m}" for m in missing))


def test_capability_yamls_exist():
    """All 18 capability YAML files must exist in the registry."""
    registry_root = Path(__file__).parent.parent / "agent-skill-registry" / "capabilities"
    expected = [
        "agent.request.normalize.yaml",
        "agent.goal.interpret.yaml",
        "agent.criteria.define.yaml",
        "agent.catalog.search.yaml",
        "agent.catalog.rank.yaml",
        "agent.catalog.detect.yaml",
        "agent.task.plan.yaml",
        "agent.plan.split.yaml",
        "agent.plan.map.yaml",
        "agent.plan.validate.yaml",
        "agent.plan.reconcile.yaml",
        "agent.plan.synthesize.yaml",
        "agent.plan.gate.yaml",
        "agent.plan.run.yaml",
        "agent.output.generate.yaml",
        "agent.output.synthesize.yaml",
        "eval.output.validate.yaml",
        "ops.trace.summarize.yaml",
    ]
    missing = [f for f in expected if not (registry_root / f).exists()]
    if missing:
        raise AssertionError(
            "Missing capability YAML files:\n" + "\n".join(f"  - {f}" for f in missing)
        )


# ---------------------------------------------------------------------------
# Test registry
# ---------------------------------------------------------------------------

TESTS = [
    ("agent.request.normalize", test_agent_request_normalize),
    ("agent.goal.interpret", test_agent_goal_interpret),
    ("agent.criteria.define", test_agent_criteria_define),
    ("agent.catalog.search", test_agent_catalog_search),
    ("agent.catalog.rank", test_agent_catalog_rank),
    ("agent.catalog.detect", test_agent_catalog_detect),
    ("agent.task.plan", test_agent_task_plan),
    ("agent.plan.split", test_agent_plan_split),
    ("agent.plan.map", test_agent_plan_map),
    ("agent.plan.validate (valid)", test_agent_plan_validate),
    ("agent.plan.validate (bad deps)", test_agent_plan_validate_detects_bad_deps),
    ("agent.plan.reconcile", test_agent_plan_reconcile),
    ("agent.plan.synthesize", test_agent_plan_synthesize),
    ("agent.plan.gate", test_agent_plan_gate),
    ("agent.plan.run", test_agent_plan_run),
    ("agent.output.generate", test_agent_output_generate),
    ("agent.output.synthesize", test_agent_output_synthesize),
    ("eval.output.validate", test_eval_output_validate),
    ("ops.trace.summarize", test_ops_trace_summarize),
    ("binding_files_exist", test_binding_files_exist),
    ("capability_yamls_exist", test_capability_yamls_exist),
]


def main():
    filter_ids = set(sys.argv[1:]) if len(sys.argv) > 1 else None
    tests_to_run = (
        [(n, fn) for n, fn in TESTS if n in filter_ids] if filter_ids else TESTS
    )

    print(f"\nRunning {len(tests_to_run)} multipurpose agent capability tests...\n")

    passed = 0
    failed = 0
    failures = []

    for name, fn in tests_to_run:
        ok = run_test(name, fn)
        if ok:
            passed += 1
        else:
            failed += 1
            failures.append(name)

    print(f"\n{'=' * 70}")
    print(f"  RESULTS: {passed} passed, {failed} failed")
    if failures:
        print("  FAILURES:")
        for f in failures:
            print(f"    - {f}")
    print(f"{'=' * 70}\n")

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()

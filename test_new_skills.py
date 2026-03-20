#!/usr/bin/env python3
"""
End-to-end test for the 6 new cognitive skills.

Tests each skill by:
  1. Building the ExecutionEngine with full binding resolution
  2. Loading test inputs from test_inputs/
  3. Executing each skill
  4. Reporting status, steps completed, outputs, and errors

Usage:
  python test_new_skills.py              # run all 6
  python test_new_skills.py decision.make analysis.compare  # run specific ones
"""

import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, ".")
from cli.main import _build_engine
from runtime.models import ExecutionRequest

REGISTRY_ROOT = Path("../agent-skill-registry")
RUNTIME_ROOT = Path(".")

SKILLS = [
    {
        "skill_id": "decision.make",
        "input_file": "test_inputs/decision_make.json",
        "expected_outputs": [
            "recommendation",
            "alternatives_considered",
            "confidence_score",
            "confidence_level",
        ],
    },
    {
        "skill_id": "analysis.compare",
        "input_file": "test_inputs/analysis_compare.json",
        "expected_outputs": [
            "analyzed_options",
            "scored_options",
            "criteria_used",
            "comparative_summary",
            "tradeoffs",
        ],
    },
    {
        "skill_id": "eval.validate",
        "input_file": "test_inputs/eval_validate.json",
        "expected_outputs": [],
    },
    {
        "skill_id": "task.frame",
        "input_file": "test_inputs/task_frame.json",
        "expected_outputs": [
            "problem_statement",
            "task_type",
            "objectives",
            "recommended_approach",
            "suggested_next_skills",
        ],
    },
    {
        "skill_id": "analysis.decompose",
        "input_file": "test_inputs/analysis_decompose.json",
        "expected_outputs": [
            "decomposition_strategy",
            "components",
            "gaps",
            "overlaps",
        ],
    },
    {
        "skill_id": "analysis.risk-assess",
        "input_file": "test_inputs/analysis_risk_assess.json",
        "expected_outputs": [
            "identified_risks",
            "critical_assumptions",
            "failure_modes",
            "mitigation_ideas",
        ],
    },
]


def run_skill_test(engine, spec):
    skill_id = spec["skill_id"]
    input_file = spec["input_file"]
    expected = spec["expected_outputs"]

    print(f"\n{'='*70}")
    print(f"  SKILL: {skill_id}")
    print(f"{'='*70}")

    with open(input_file, encoding="utf-8") as f:
        inputs = json.load(f)

    trace_id = f"test-{skill_id.replace('.', '-')}-001"
    req = ExecutionRequest(skill_id=skill_id, inputs=inputs, trace_id=trace_id)

    try:
        result = engine.execute(req)
    except Exception as exc:
        print(f"  STATUS       : EXCEPTION")
        print(f"  ERROR        : {exc}")
        return False

    print(f"  STATUS       : {result.status}")
    steps_done = len(result.state.step_results) if hasattr(result, 'state') and result.state else 0
    print(f"  STEPS        : {steps_done}")
    duration = getattr(result.state, 'duration_ms', 0) if hasattr(result, 'state') and result.state else 0
    print(f"  DURATION_MS  : {round(duration)}")

    if result.status != "completed":
        print(f"  ERROR        : {getattr(result, 'error', 'N/A')}")
        return False

    output_keys = sorted(result.outputs.keys()) if result.outputs else []
    print(f"  OUTPUT_KEYS  : {output_keys}")

    # Check expected outputs
    missing = [k for k in expected if k not in (result.outputs or {})]
    if missing:
        print(f"  MISSING KEYS : {missing}")

    # Write result to file
    out_path = f"test_results/{skill_id.replace('.', '_')}.json"
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result.outputs, f, indent=2, ensure_ascii=False, default=str)
    print(f"  RESULT FILE  : {out_path}")

    return True


def main():
    filter_ids = set(sys.argv[1:]) if len(sys.argv) > 1 else None

    print("Building execution engine...")
    engine = _build_engine(REGISTRY_ROOT, RUNTIME_ROOT, None, None)
    print("Engine ready.\n")

    skills_to_test = SKILLS
    if filter_ids:
        skills_to_test = [s for s in SKILLS if s["skill_id"] in filter_ids]

    passed = 0
    failed = 0
    errors = []

    for spec in skills_to_test:
        try:
            ok = run_skill_test(engine, spec)
            if ok:
                passed += 1
            else:
                failed += 1
                errors.append(spec["skill_id"])
        except Exception:
            failed += 1
            errors.append(spec["skill_id"])
            print(f"  EXCEPTION:")
            traceback.print_exc()

    print(f"\n{'='*70}")
    print(f"  SUMMARY: {passed} passed, {failed} failed out of {passed + failed}")
    if errors:
        print(f"  FAILED : {errors}")
    print(f"{'='*70}")

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()

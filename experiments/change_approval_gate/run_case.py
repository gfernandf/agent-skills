"""
Change Approval Gate — Experiment Runner
=========================================
Run the code.change-approval-gate ORCA skill against a fixture and policy,
optionally compare against a direct prompt-based baseline.

Usage:
    cd c:\\Users\\Usuario\\agent-skills

    # Run ORCA on a single fixture (standard policy by default)
    python experiments/change_approval_gate/run_case.py --fixture f01_refactor_innocuous

    # Specify a policy profile explicitly
    python experiments/change_approval_gate/run_case.py --fixture f06_hardcoded_secret --policy strict_prod

    # Run both ORCA and prompt baseline side-by-side
    python experiments/change_approval_gate/run_case.py --fixture f07_release_no_test_evidence --compare

    # Run ALL fixtures against ALL policies (saves CSV summary to outputs/)
    python experiments/change_approval_gate/run_case.py --all

Requires: OPENAI_API_KEY environment variable.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent.parent   # agent-skills/
REGISTRY_ROOT = REPO_ROOT.parent / "agent-skill-registry"   # sibling repo
CASE_DIR = REPO_ROOT / "experiments" / "change_approval_gate"
FIXTURES_DIR = CASE_DIR / "fixtures"
POLICIES_DIR = CASE_DIR / "policies"
PROMPTS_DIR = CASE_DIR / "prompts"
OUTPUT_DIR = CASE_DIR / "outputs"
EXPERIMENTS_SKILLS_DIR = REPO_ROOT / "experiments" / "skills"

sys.path.insert(0, str(REPO_ROOT))

SKILL_ID = "code.change-approval-gate"

# ---------------------------------------------------------------------------
# LLM client (mirrors run_benchmark.py exactly)
# ---------------------------------------------------------------------------
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
MODEL = "gpt-4o-mini"
SEED = 42


def _llm_call(messages: list[dict], temperature: float = 0.2) -> dict:
    """Direct OpenAI chat completions call. Returns usage + content."""
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY not set")

    payload = json.dumps(
        {
            "model": MODEL,
            "messages": messages,
            "temperature": temperature,
            "seed": SEED,
            "response_format": {"type": "json_object"},
        }
    ).encode()

    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=payload,
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=120) as resp:
        body = json.loads(resp.read())
    latency_s = time.perf_counter() - t0

    content_raw = body["choices"][0]["message"]["content"]
    usage = body.get("usage", {})

    try:
        content = json.loads(content_raw)
    except json.JSONDecodeError:
        content = {"_raw": content_raw}

    return {
        "content": content,
        "latency_s": round(latency_s, 3),
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
        "total_tokens": usage.get("total_tokens", 0),
    }


# ---------------------------------------------------------------------------
# ORCA engine helper (mirrors run_benchmark.py exactly)
# ---------------------------------------------------------------------------
def _build_orca_engine():
    """Build the ORCA runtime engine."""
    import logging
    logging.getLogger("runtime").setLevel(logging.WARNING)
    from runtime.engine_factory import build_runtime_components

    components = build_runtime_components(
        registry_root=REGISTRY_ROOT,
        runtime_root=REPO_ROOT,
        host_root=REPO_ROOT,
        local_skills_root=EXPERIMENTS_SKILLS_DIR,
    )
    return components.engine


def _run_orca_skill(engine, skill_id: str, inputs: dict) -> dict:
    """Execute an ORCA skill and return outputs + metrics."""
    from runtime.models import ExecutionRequest, ExecutionOptions

    request = ExecutionRequest(
        skill_id=skill_id,
        inputs=inputs,
        options=ExecutionOptions(
            required_conformance_profile=None,
            trace_enabled=True,
        ),
        trace_id=f"cag-{hashlib.md5(json.dumps(inputs, sort_keys=True).encode()).hexdigest()[:8]}",
        channel="experiment",
    )

    t0 = time.perf_counter()
    result = engine.execute(request)
    latency_s = time.perf_counter() - t0

    step_trace = []
    if result.state and hasattr(result.state, "step_results"):
        for sid, sr in result.state.step_results.items():
            step_trace.append(
                {
                    "step_id": sr.step_id,
                    "uses": sr.uses,
                    "status": sr.status,
                    "latency_ms": sr.latency_ms,
                }
            )

    return {
        "outputs": result.outputs,
        "status": result.status,
        "latency_s": round(latency_s, 3),
        "step_trace": step_trace,
    }


# ---------------------------------------------------------------------------
# Prompt baseline
# ---------------------------------------------------------------------------
def run_prompt(fixture: dict, policy: dict) -> dict:
    """Run the single-prompt baseline."""
    template = (PROMPTS_DIR / "baseline_prompt.txt").read_text(encoding="utf-8")
    prompt_text = template.format(
        change_package_json=json.dumps(fixture["change_package"], indent=2),
        policy_profile_json=json.dumps(policy, indent=2),
    )
    messages = [
        {
            "role": "system",
            "content": "You are a change approval reviewer. Always respond with valid JSON.",
        },
        {"role": "user", "content": prompt_text},
    ]
    result = _llm_call(messages)
    return {
        "approach": "prompt",
        "output": result["content"],
        "latency_s": result["latency_s"],
        "total_tokens": result["total_tokens"],
        "traceable": False,
        "step_trace": [],
    }


# ---------------------------------------------------------------------------
# ORCA runner
# ---------------------------------------------------------------------------
def run_orca(engine, fixture: dict, policy: dict) -> dict:
    """Run the ORCA change-approval-gate skill."""
    pkg = fixture["change_package"]
    inputs = {
        "change_package": pkg,
        "diff_text": pkg.get("diff_text", ""),
        "author_summary": pkg.get("author_summary", ""),
        "policy_gate": policy["gate"],
        "policy_name": policy.get("name", ""),
    }
    result = _run_orca_skill(engine, SKILL_ID, inputs)
    return {
        "approach": "orca",
        "output": result["outputs"],
        "latency_s": result["latency_s"],
        "total_tokens": 0,
        "traceable": len(result["step_trace"]) > 0,
        "step_trace": result["step_trace"],
        "status": result["status"],
    }


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------
def _print_result(label: str, result: dict, fixture_meta: dict) -> None:
    out = result["output"]
    expected = fixture_meta.get("expected_decision", "?")
    decision = out.get("decision", "?") if isinstance(out, dict) else "?"
    match = "✓" if decision == expected else "✗"

    print(f"\n{'=' * 60}")
    print(f"  {label}")
    print(f"{'=' * 60}")
    print(f"  Decision:         {decision}  [{match} expected: {expected}]")
    print(f"  Risk level:       {out.get('risk_level', '?')}")
    print(f"  Confidence:       {out.get('confidence', '?')}")
    print(f"  Latency:          {result['latency_s']}s")
    print(f"  Traceable:        {result['traceable']}")
    if result.get("step_trace"):
        print(f"  Steps executed:   {len(result['step_trace'])}")
        for step in result["step_trace"]:
            print(f"    [{step.get('status', '?')}] {step['step_id']} ({step['uses']})")
    violated = out.get("violated_rules", [])
    if violated:
        print("  Violated rules:")
        for v in violated:
            print(f"    - {v}")
    followups = out.get("required_followups", [])
    if followups:
        print("  Required followups:")
        for f in followups:
            print(f"    - {f}")
    rationale = out.get("rationale", "")
    if rationale:
        print(f"  Rationale:  {rationale[:300]}{'...' if len(rationale) > 300 else ''}")
    print()


def _print_comparison_table(rows: list[dict]) -> None:
    print("\n" + "=" * 100)
    print("  COMPARISON SUMMARY")
    print("=" * 100)
    header = f"{'Fixture':<40} {'Policy':<14} {'Expected':<10} {'Prompt':<10} {'ORCA':<10} {'P-Match':<8} {'O-Match':<8}"
    print(header)
    print("-" * 100)
    for r in rows:
        pm = "✓" if r["prompt_decision"] == r["expected"] else "✗"
        om = "✓" if r["orca_decision"] == r["expected"] else "✗"
        print(
            f"{r['fixture_id']:<40} {r['policy']:<14} {r['expected']:<10} "
            f"{r['prompt_decision']:<10} {r['orca_decision']:<10} {pm:<8} {om:<8}"
        )
    total = len(rows)
    p_correct = sum(1 for r in rows if r["prompt_decision"] == r["expected"])
    o_correct = sum(1 for r in rows if r["orca_decision"] == r["expected"])
    print("-" * 100)
    print(f"{'TOTAL':<40} {'':14} {'':10} {'':10} {'':10} {p_correct}/{total}  {o_correct}/{total}")
    print()


# ---------------------------------------------------------------------------
# All-fixtures runner
# ---------------------------------------------------------------------------
def run_all(engine) -> None:
    """Run every fixture against every policy, save CSV, print comparison."""
    fixture_files = sorted(FIXTURES_DIR.glob("f*.json"))
    policy_files = sorted(POLICIES_DIR.glob("*.json"))
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    rows = []
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    for fpath in fixture_files:
        fixture = json.loads(fpath.read_text(encoding="utf-8"))
        meta = fixture.get("_meta", {})
        for ppath in policy_files:
            policy = json.loads(ppath.read_text(encoding="utf-8"))
            print(f"\nRunning: {fpath.stem} × {ppath.stem} ...", end="", flush=True)

            try:
                pr = run_prompt(fixture, policy)
                pr_decision = pr["output"].get("decision", "error") if isinstance(pr["output"], dict) else "error"
            except Exception as e:
                pr_decision = f"error: {e}"
                pr = {"output": {}, "latency_s": 0, "total_tokens": 0, "traceable": False, "step_trace": []}

            try:
                or_ = run_orca(engine, fixture, policy)
                or_decision = or_["output"].get("decision", "error") if isinstance(or_["output"], dict) else "error"
            except Exception as e:
                or_decision = f"error: {e}"
                or_ = {"output": {}, "latency_s": 0, "total_tokens": 0, "traceable": False, "step_trace": [], "status": "error"}

            print(f" prompt={pr_decision} orca={or_decision}")
            rows.append(
                {
                    "fixture_id": fpath.stem,
                    "policy": ppath.stem,
                    "expected": meta.get("expected_decision", "?"),
                    "prompt_decision": pr_decision,
                    "orca_decision": or_decision,
                    "prompt_latency_s": pr["latency_s"],
                    "orca_latency_s": or_["latency_s"],
                    "orca_traceable": or_["traceable"],
                    "orca_steps": len(or_.get("step_trace", [])),
                }
            )

    # Save CSV
    csv_path = OUTPUT_DIR / f"run_all_{timestamp}.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nResults saved → {csv_path.relative_to(REPO_ROOT)}")

    _print_comparison_table(rows)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run Change Approval Gate experiment fixtures"
    )
    parser.add_argument(
        "--fixture",
        help="Fixture stem (e.g. f01_refactor_innocuous). Omit for --all.",
    )
    parser.add_argument(
        "--policy",
        default="standard",
        help="Policy file stem (fast_track | standard | strict_prod). Default: standard",
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Run both prompt baseline and ORCA and show side-by-side.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run all fixtures × all policies and save CSV summary.",
    )
    args = parser.parse_args()

    if not OPENAI_API_KEY:
        print("ERROR: OPENAI_API_KEY not set.", file=sys.stderr)
        sys.exit(1)

    print("Building ORCA engine …")
    engine = _build_orca_engine()
    print("Engine ready.\n")

    if args.all:
        run_all(engine)
        return

    if not args.fixture:
        parser.error("--fixture is required unless --all is specified")

    # Load fixture
    fpath = FIXTURES_DIR / f"{args.fixture}.json"
    if not fpath.exists():
        # Try prefix match
        matches = list(FIXTURES_DIR.glob(f"{args.fixture}*.json"))
        if len(matches) == 1:
            fpath = matches[0]
        else:
            print(f"ERROR: fixture not found: {args.fixture}", file=sys.stderr)
            sys.exit(1)

    fixture = json.loads(fpath.read_text(encoding="utf-8"))
    meta = fixture.get("_meta", {})

    # Load policy
    ppath = POLICIES_DIR / f"{args.policy}.json"
    if not ppath.exists():
        print(f"ERROR: policy not found: {args.policy}", file=sys.stderr)
        sys.exit(1)

    policy = json.loads(ppath.read_text(encoding="utf-8"))

    print(f"Fixture:  {fpath.stem}")
    print(f"Policy:   {policy['name']}")
    print(f"Expected: {meta.get('expected_decision', 'unknown')}")
    print(f"Teaching: {meta.get('teaching_point', '')}")

    if args.compare:
        print("\nRunning prompt baseline …")
        pr = run_prompt(fixture, policy)
        print("Running ORCA skill …")
        or_ = run_orca(engine, fixture, policy)
        _print_result("PROMPT BASELINE", pr, meta)
        _print_result("ORCA: code.change-approval-gate", or_, meta)
    else:
        print("\nRunning ORCA skill …")
        or_ = run_orca(engine, fixture, policy)
        _print_result("ORCA: code.change-approval-gate", or_, meta)


if __name__ == "__main__":
    main()

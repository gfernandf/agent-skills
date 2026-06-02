#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REPORT = ROOT / "artifacts" / "replay_determinism_report.json"

TEST_NODES: list[str] = [
    "runtime/test_durability_advanced.py::test_checkpoint_state_equivalence_after_partial_progress",
    "test_neutral_api_slice2.py::test_resume_run_executes_from_checkpoint",
    "test_neutral_api_slice2.py::test_replay_run_executes_from_checkpoint",
]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Verify replay determinism by repeating canonical checkpoint resume/replay "
            "tests and requiring stable pass outcomes on every repetition."
        )
    )
    parser.add_argument(
        "--report-file",
        type=Path,
        default=DEFAULT_REPORT,
        help="Path to write JSON report.",
    )
    parser.add_argument(
        "--repetitions",
        type=int,
        default=2,
        help="How many times to run each deterministic replay test node.",
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Continue running remaining test executions after failures.",
    )
    return parser.parse_args()


def _run_test(nodeid: str) -> tuple[int, float]:
    command = [sys.executable, "-m", "pytest", "-q", "-o", "addopts=", nodeid]
    env = dict(os.environ)
    env["PYTEST_ADDOPTS"] = ""
    start = time.perf_counter()
    proc = subprocess.run(command, cwd=ROOT, env=env)
    elapsed = time.perf_counter() - start
    return proc.returncode, elapsed


def main() -> int:
    args = _parse_args()
    args.report_file.parent.mkdir(parents=True, exist_ok=True)

    repetitions = max(1, int(args.repetitions or 1))
    print("Running replay determinism verification...")
    print(f"- repetitions: {repetitions}")

    executions: list[dict[str, object]] = []
    failures: list[str] = []

    expected_total_executions = len(TEST_NODES) * repetitions
    completed_executions = 0

    for nodeid in TEST_NODES:
        for repetition in range(1, repetitions + 1):
            print(f"[replay-determinism] pass={repetition}/{repetitions} pytest -q {nodeid}")
            rc, elapsed = _run_test(nodeid)
            completed_executions += 1
            execution_id = f"{nodeid}::pass{repetition}"
            executions.append(
                {
                    "nodeid": nodeid,
                    "repetition": repetition,
                    "returncode": rc,
                    "duration_seconds": round(elapsed, 3),
                    "execution_id": execution_id,
                }
            )
            if rc != 0:
                failures.append(execution_id)
                if not args.continue_on_error:
                    break
        if failures and not args.continue_on_error:
            break

    passed_executions = sum(1 for item in executions if item.get("returncode") == 0)
    all_passed = len(failures) == 0

    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "status": "passed" if all_passed else "failed",
        "contract": "replay_determinism_v1",
        "summary": {
            "test_nodes": len(TEST_NODES),
            "repetitions": repetitions,
            "expected_total_executions": expected_total_executions,
            "completed_executions": completed_executions,
            "execution_complete": completed_executions == expected_total_executions,
            "passed_executions": passed_executions,
            "failed_executions": len(executions) - passed_executions,
            "pass_ratio": (
                float(passed_executions) / float(len(executions))
                if executions
                else 0.0
            ),
        },
        "tests": executions,
        "failures": failures,
    }

    args.report_file.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("\nReplay determinism summary")
    print(f"- passed: {passed_executions}/{len(executions)}")
    print(f"- status: {report['status']}")
    print(f"- report: {args.report_file}")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

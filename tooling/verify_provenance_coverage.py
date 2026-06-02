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
DEFAULT_REPORT = ROOT / "artifacts" / "provenance_coverage_report.json"

TEST_NODES: list[str] = [
    "runtime/test_checkpoint.py::TestCheckpointRoundTrip::test_round_trip_dict",
    "runtime/test_durability_advanced.py::test_replay_and_fork_preserve_lineage_metadata_integrity",
    "runtime/test_durability_advanced.py::test_checkpoint_record_includes_state_snapshot_reference_integrity",
    "runtime/test_run_store.py::test_replay_run",
    "runtime/test_run_store.py::test_fork_run",
    "test_neutral_api_slice2.py::test_replay_run_executes_from_checkpoint",
    "test_neutral_api_slice2.py::test_replay_run_propagates_tenant_to_replay_execution",
    "test_neutral_api_slice2.py::test_fork_run_creates_new_pending_run",
]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Verify broader provenance coverage across checkpoint serialization, "
            "run lineage metadata, and replay/fork provenance propagation."
        )
    )
    parser.add_argument(
        "--report-file",
        type=Path,
        default=DEFAULT_REPORT,
        help="Path to write JSON report.",
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Continue running all test nodes even when one fails.",
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

    print("Running provenance coverage verification...")

    tests: list[dict[str, object]] = []
    failures: list[str] = []

    for nodeid in TEST_NODES:
        print(f"[provenance-coverage] pytest -q {nodeid}")
        rc, elapsed = _run_test(nodeid)
        tests.append(
            {
                "nodeid": nodeid,
                "returncode": rc,
                "duration_seconds": round(elapsed, 3),
            }
        )
        if rc != 0:
            failures.append(nodeid)
            if not args.continue_on_error:
                break

    passed = sum(1 for item in tests if item.get("returncode") == 0)
    total = len(tests)
    expected_total = len(TEST_NODES)

    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "status": "passed" if not failures else "failed",
        "contract": "provenance_coverage_v1",
        "summary": {
            "total_tests": total,
            "expected_total_tests": expected_total,
            "test_execution_complete": total == expected_total,
            "passed_tests": passed,
            "failed_tests": total - passed,
            "pass_ratio": (float(passed) / float(total)) if total else 0.0,
        },
        "tests": tests,
        "failures": failures,
    }

    args.report_file.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("\nProvenance coverage summary")
    print(f"- passed: {passed}/{total}")
    print(f"- status: {report['status']}")
    print(f"- report: {args.report_file}")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

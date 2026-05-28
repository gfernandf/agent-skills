#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REPORT = ROOT / "artifacts" / "durability_contract_report.json"


@dataclass
class TestResult:
    nodeid: str
    returncode: int
    duration_seconds: float


TEST_NODES: list[str] = [
    "runtime/test_checkpoint.py",
    "runtime/test_checkpoint_manager.py",
    "runtime/test_run_store.py",
    "test_neutral_api_slice2.py::test_resume_run_executes_from_checkpoint",
    "test_neutral_api_slice2.py::test_replay_run_executes_from_checkpoint",
    "test_neutral_api_slice2.py::test_fork_run_creates_new_pending_run",
]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Verify ORCA durability contract baseline with canonical checkpoint and run lifecycle tests."
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


def _run_test(nodeid: str) -> TestResult:
    command = [sys.executable, "-m", "pytest", "-q", nodeid]
    start = time.perf_counter()
    proc = subprocess.run(command, cwd=ROOT)
    duration = time.perf_counter() - start
    return TestResult(
        nodeid=nodeid,
        returncode=proc.returncode,
        duration_seconds=duration,
    )


def main() -> int:
    args = _parse_args()
    args.report_file.parent.mkdir(parents=True, exist_ok=True)

    print("Running durability contract verification...")

    results: list[TestResult] = []
    failures: list[str] = []

    for nodeid in TEST_NODES:
        print(f"[durability] pytest -q {nodeid}")
        result = _run_test(nodeid)
        results.append(result)
        if result.returncode != 0:
            failures.append(nodeid)
            if not args.continue_on_error:
                break

    passed = sum(1 for r in results if r.returncode == 0)
    total = len(results)
    ratio = (passed / total) if total else 0.0

    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "status": "passed" if not failures else "failed",
        "contract": "durability_v1",
        "summary": {
            "total": total,
            "passed": passed,
            "failed": total - passed,
            "pass_ratio": ratio,
        },
        "tests": [
            {
                "nodeid": r.nodeid,
                "returncode": r.returncode,
                "duration_seconds": round(r.duration_seconds, 3),
            }
            for r in results
        ],
        "failures": failures,
    }

    args.report_file.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("\nDurability contract summary")
    print(f"- passed: {passed}/{total}")
    print(f"- pass_ratio: {ratio:.3f}")
    print(f"- report: {args.report_file}")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

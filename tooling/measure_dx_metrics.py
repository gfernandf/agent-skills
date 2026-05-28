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
DEFAULT_REPORT = ROOT / "artifacts" / "dx_metrics.json"


@dataclass
class StepResult:
    name: str
    command: list[str]
    returncode: int
    duration_seconds: float


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Measure developer-experience baseline metrics for onboarding and parity checks."
        )
    )
    parser.add_argument(
        "--report-file",
        type=Path,
        default=DEFAULT_REPORT,
        help="Path to write the DX metrics JSON report.",
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Run all steps even if one fails.",
    )
    return parser.parse_args()


def _run_step(name: str, command: list[str]) -> StepResult:
    start = time.perf_counter()
    proc = subprocess.run(command, cwd=ROOT)
    duration = time.perf_counter() - start
    return StepResult(
        name=name,
        command=command,
        returncode=proc.returncode,
        duration_seconds=duration,
    )


def main() -> int:
    args = _parse_args()

    args.report_file.parent.mkdir(parents=True, exist_ok=True)

    # These checks are explicitly tied to onboarding and customer-facing docs.
    steps: list[tuple[str, list[str]]] = [
        (
            "smoke_baseline",
            [
                sys.executable,
                "tooling/verify_smoke_capabilities.py",
                "--report-file",
                "artifacts/smoke_report.json",
            ],
        ),
        (
            "customer_facing_neutral",
            [sys.executable, "tooling/verify_customer_facing_neutral.py"],
        ),
        (
            "customer_http_controls",
            [sys.executable, "tooling/verify_customer_http_controls.py"],
        ),
        (
            "customer_parity_snapshot",
            [sys.executable, "tooling/verify_customer_facing_parity_snapshot.py"],
        ),
    ]

    results: list[StepResult] = []
    failures: list[str] = []
    cumulative_time = 0.0
    time_to_first_success_seconds: float | None = None

    print("Running DX metrics checks...")

    for name, command in steps:
        print(f"[dx] {name}: {' '.join(command)}")
        result = _run_step(name, command)
        results.append(result)
        cumulative_time += result.duration_seconds

        if result.returncode == 0 and time_to_first_success_seconds is None:
            time_to_first_success_seconds = cumulative_time

        if result.returncode != 0:
            failures.append(name)
            if not args.continue_on_error:
                break

    executed = len(results)
    passed = sum(1 for r in results if r.returncode == 0)
    docs_parity_score = (passed / executed) if executed else 0.0

    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "status": "passed" if not failures else "failed",
        "metrics": {
            "time_to_first_success_seconds": time_to_first_success_seconds,
            "docs_parity_score": docs_parity_score,
            "checks_total": executed,
            "checks_passed": passed,
            "checks_failed": executed - passed,
        },
        "steps": [
            {
                "name": r.name,
                "command": " ".join(r.command),
                "returncode": r.returncode,
                "duration_seconds": round(r.duration_seconds, 3),
            }
            for r in results
        ],
        "failures": failures,
        "notes": [
            "time_to_first_success_seconds is measured from first DX check start to first passing check.",
            "docs_parity_score is pass ratio across onboarding/customer-facing verification checks executed by this script.",
        ],
    }

    args.report_file.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("\nDX metrics summary")
    print(f"- checks: {passed}/{executed} passed")
    print(f"- docs_parity_score: {docs_parity_score:.3f}")
    if time_to_first_success_seconds is None:
        print("- time_to_first_success_seconds: n/a")
    else:
        print(f"- time_to_first_success_seconds: {time_to_first_success_seconds:.3f}")
    print(f"- report: {args.report_file}")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

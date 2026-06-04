#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REPORT_PATH = ROOT / "artifacts" / "cognitive_quality_gates_local_report.json"

GATE_COMMANDS: list[list[str]] = [
    ["-m", "pytest", "-q", "test_cognitive_capabilities_e2e.py", "-o", "addopts="],
    ["-m", "pytest", "-q", "test_cognitive_semantic_golden.py", "-o", "addopts="],
    ["-m", "pytest", "-q", "test_cognitive_semantic_all.py", "-o", "addopts="],
    ["-m", "pytest", "-q", "test_option_integrity_phase1.py", "-o", "addopts="],
    ["-m", "pytest", "-q", "test_confidence_redesign.py", "-o", "addopts="],
    [
        "-m",
        "pytest",
        "-q",
        "test_confidence_calibration_production.py",
        "-o",
        "addopts=",
    ],
    ["-m", "pytest", "-q", "test_decision_make_audit_contract.py", "-o", "addopts="],
    ["-m", "pytest", "-q", "test_openapi_runtime_guardrails.py", "-o", "addopts="],
    ["-m", "pytest", "-q", "test_alternatives_evaluated.py", "-o", "addopts="],
    ["test_alternatives_simple.py"],
    [
        "tooling/generate_cognitive_quality_scorecard.py",
        "--fail-on-threshold",
        "--min-axis",
        "9.0",
        "--min-overall",
        "9.0",
    ],
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the cognitive-quality-gates test block used in CI."
    )
    parser.add_argument(
        "--report-file",
        type=Path,
        default=DEFAULT_REPORT_PATH,
        help="Path for JSON report output.",
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Run all commands and report all failures instead of failing fast.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Print commands and exit without executing.",
    )
    return parser.parse_args()


def _run_command(command: list[str]) -> tuple[int, float, str, str]:
    cmd = [sys.executable, *command]
    start = time.perf_counter()
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    duration = time.perf_counter() - start
    return proc.returncode, duration, proc.stdout, proc.stderr


def main() -> int:
    args = parse_args()

    if args.list:
        print("Cognitive quality gate commands:")
        for item in GATE_COMMANDS:
            print(f"- {sys.executable} {' '.join(item)}")
        return 0

    args.report_file.parent.mkdir(parents=True, exist_ok=True)

    report: dict[str, object] = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "root": str(ROOT),
        "python": sys.executable,
        "commands": [],
    }

    failures: list[str] = []
    total_duration = 0.0

    print("Running cognitive-quality-gates...")
    for command in GATE_COMMANDS:
        rc, duration, stdout, stderr = _run_command(command)
        total_duration += duration

        rendered = f"{sys.executable} {' '.join(command)}"
        print(f"\n[gate] {rendered}")
        print(f"[rc={rc}] [duration_s={duration:.2f}]")

        lines = (stdout + "\n" + stderr).splitlines()
        for line in lines[-40:]:
            print(line)

        report["commands"].append(
            {
                "command": rendered,
                "returncode": rc,
                "duration_seconds": round(duration, 3),
            }
        )

        if rc != 0:
            failures.append(rendered)
            if not args.continue_on_error:
                break

    report["total_duration_seconds"] = round(total_duration, 3)
    report["status"] = "failed" if failures else "passed"
    report["failures"] = failures
    args.report_file.write_text(json.dumps(report, indent=2), encoding="utf-8")

    if failures:
        print("\nCognitive quality gates failed:")
        for item in failures:
            print(f"- {item}")
        print(f"Report: {args.report_file}")
        return 1

    print("\nCognitive quality gates passed.")
    print(f"Report: {args.report_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

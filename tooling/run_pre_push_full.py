#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REPORT = ROOT / "artifacts" / "pre_push_full_report.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run consolidated pre-push full checks for agent-skills."
    )
    parser.add_argument(
        "--report-file",
        type=Path,
        default=DEFAULT_REPORT,
        help="Path for JSON report output.",
    )
    parser.add_argument(
        "--skip-customer-facing",
        action="store_true",
        help="Skip customer-facing neutral/controls/parity verifiers.",
    )
    parser.add_argument(
        "--skip-legacy-report",
        action="store_true",
        help="Skip legacy bindings report generation.",
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Run all steps and report all failures instead of failing fast.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Print commands and exit without executing.",
    )
    return parser.parse_args()


def _build_steps(args: argparse.Namespace) -> list[list[str]]:
    steps: list[list[str]] = [
        ["tooling/run_cognitive_quality_gates.py"],
    ]

    if not args.skip_customer_facing:
        steps.extend(
            [
                ["tooling/verify_customer_facing_neutral.py"],
                ["tooling/verify_customer_http_controls.py"],
                ["tooling/verify_customer_facing_parity_snapshot.py"],
            ]
        )

    if not args.skip_legacy_report:
        steps.append(["tooling/report_legacy_bindings.py"])

    return steps


def _run(command: list[str]) -> tuple[int, float, str, str, str]:
    cmd = [sys.executable, *command]
    rendered = f"{sys.executable} {' '.join(command)}"
    start = time.perf_counter()
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    duration = time.perf_counter() - start
    return proc.returncode, duration, proc.stdout, proc.stderr, rendered


def main() -> int:
    args = parse_args()
    steps = _build_steps(args)

    if args.list:
        print("Pre-push full commands:")
        for step in steps:
            print(f"- {sys.executable} {' '.join(step)}")
        return 0

    args.report_file.parent.mkdir(parents=True, exist_ok=True)

    summary: dict[str, object] = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "root": str(ROOT),
        "python": sys.executable,
        "status": "running",
        "steps": [],
    }

    failures: list[str] = []
    total_duration = 0.0

    print("Running pre-push full checks...")
    for step in steps:
        rc, duration, stdout, stderr, rendered = _run(step)
        total_duration += duration

        print(f"\n[step] {rendered}")
        print(f"[rc={rc}] [duration_s={duration:.2f}]")
        for line in (stdout + "\n" + stderr).splitlines()[-40:]:
            print(line)

        summary["steps"].append(
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

    summary["total_duration_seconds"] = round(total_duration, 3)
    summary["status"] = "failed" if failures else "passed"
    summary["failures"] = failures
    args.report_file.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    if failures:
        print("\nPre-push full checks failed:")
        for item in failures:
            print(f"- {item}")
        print(f"Report: {args.report_file}")
        return 1

    print("\nPre-push full checks passed.")
    print(f"Report: {args.report_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REPORT = ROOT / "artifacts" / "durability_advanced_report.json"


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    description: str
    test_nodes: tuple[str, ...]


SCENARIOS: tuple[Scenario, ...] = (
    Scenario(
        scenario_id="restart_continuity",
        description="Resume from checkpoint preserves continuation semantics.",
        test_nodes=(
            "runtime/test_durability_advanced.py::test_checkpoint_lineage_multi_boundary_roundtrip",
            "runtime/test_durability_advanced.py::test_checkpoint_state_equivalence_after_partial_progress",
            "runtime/test_durability_advanced.py::test_resume_from_waiting_signal_uses_checkpoint_pointer",
            "test_neutral_api_slice2.py::test_resume_run_executes_from_checkpoint",
            "runtime/test_step_control_flow.py::test_engine_resume_skips_completed_steps",
            "runtime/test_scheduler_functional.py::test_precompleted_steps_enable_resume",
        ),
    ),
    Scenario(
        scenario_id="replay_equivalence",
        description="Replay runs from checkpoint with deterministic linkage behavior.",
        test_nodes=(
            "runtime/test_durability_advanced.py::test_replay_and_fork_preserve_lineage_metadata_integrity",
            "test_neutral_api_slice2.py::test_replay_run_executes_from_checkpoint",
            "test_neutral_api_slice2.py::test_replay_run_uses_unique_run_ids",
            "runtime/test_run_store.py::test_replay_run",
        ),
    ),
    Scenario(
        scenario_id="failure_injection_paths",
        description="Failure/not-found durability paths fail deterministically with typed behavior.",
        test_nodes=(
            "runtime/test_step_control_flow.py::test_retry_exhaustion",
            "test_neutral_api_slice2.py::test_resume_run_missing_run_returns_not_found",
            "test_neutral_api_slice2.py::test_replay_run_missing_checkpoint_returns_not_found",
            "test_neutral_api_slice2.py::test_fork_run_missing_checkpoint_returns_not_found",
        ),
    ),
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Verify durability advanced contract scenarios: restart continuity, "
            "replay equivalence, and failure-injection not-found paths."
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
        help="Continue running all scenarios even after failures.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List scenarios/tests and exit.",
    )
    return parser.parse_args()


def _run_test_node(nodeid: str) -> tuple[int, float]:
    cmd = [sys.executable, "-m", "pytest", "-q", "-o", "addopts=", nodeid]
    env = dict(os.environ)
    env["PYTEST_ADDOPTS"] = ""
    start = time.perf_counter()
    proc = subprocess.run(cmd, cwd=ROOT, env=env)
    elapsed = time.perf_counter() - start
    return proc.returncode, elapsed


def main() -> int:
    args = _parse_args()

    if args.list:
        print("Durability advanced scenarios")
        for scenario in SCENARIOS:
            print(f"- {scenario.scenario_id}: {scenario.description}")
            for node in scenario.test_nodes:
                print(f"  - {node}")
        return 0

    args.report_file.parent.mkdir(parents=True, exist_ok=True)

    scenario_reports: list[dict[str, object]] = []
    overall_failures: list[str] = []

    print("Running durability advanced verification...")

    for scenario in SCENARIOS:
        print(f"\n[durability-advanced] scenario={scenario.scenario_id}")
        test_results: list[dict[str, object]] = []
        scenario_failed = False

        for node in scenario.test_nodes:
            print(f"  pytest -q {node}")
            rc, elapsed = _run_test_node(node)
            test_results.append(
                {
                    "nodeid": node,
                    "returncode": rc,
                    "duration_seconds": round(elapsed, 3),
                }
            )
            if rc != 0:
                scenario_failed = True
                overall_failures.append(f"{scenario.scenario_id}:{node}")
                if not args.continue_on_error:
                    break

        passed = sum(1 for item in test_results if item["returncode"] == 0)
        total = len(test_results)
        pass_ratio = (passed / total) if total else 0.0

        scenario_reports.append(
            {
                "scenario_id": scenario.scenario_id,
                "description": scenario.description,
                "status": "passed" if not scenario_failed else "failed",
                "summary": {
                    "total": total,
                    "passed": passed,
                    "failed": total - passed,
                    "pass_ratio": pass_ratio,
                },
                "tests": test_results,
            }
        )

        if scenario_failed and not args.continue_on_error:
            break

    passed_scenarios = sum(1 for item in scenario_reports if item["status"] == "passed")
    total_scenarios = len(scenario_reports)

    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "status": "passed" if not overall_failures else "failed",
        "contract": "durability_v2_advanced",
        "summary": {
            "total_scenarios": total_scenarios,
            "passed_scenarios": passed_scenarios,
            "failed_scenarios": total_scenarios - passed_scenarios,
            "scenario_pass_ratio": (passed_scenarios / total_scenarios) if total_scenarios else 0.0,
        },
        "scenarios": scenario_reports,
        "failures": overall_failures,
    }

    args.report_file.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("\nDurability advanced summary")
    print(f"- scenarios passed: {passed_scenarios}/{total_scenarios}")
    print(f"- status: {report['status']}")
    print(f"- report: {args.report_file}")

    return 1 if overall_failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

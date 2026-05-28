#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REPORT = ROOT / "artifacts" / "policy_gate_freshness_report.json"
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
SMOKE_WORKFLOW = ROOT / ".github" / "workflows" / "smoke.yml"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Verify policy governance gate freshness in CI and smoke workflows."
        )
    )
    parser.add_argument(
        "--report-file",
        type=Path,
        default=DEFAULT_REPORT,
        help="Path to write JSON report.",
    )
    return parser.parse_args()


def _check(condition: bool, check_id: str, detail: str) -> dict[str, object]:
    return {
        "check_id": check_id,
        "passed": condition,
        "detail": detail,
    }


def main() -> int:
    args = _parse_args()
    args.report_file.parent.mkdir(parents=True, exist_ok=True)

    checks: list[dict[str, object]] = []

    checks.append(_check(CI_WORKFLOW.exists(), "ci_workflow_exists", str(CI_WORKFLOW)))
    checks.append(
        _check(
            SMOKE_WORKFLOW.exists(),
            "smoke_workflow_exists",
            str(SMOKE_WORKFLOW),
        )
    )

    ci_text = ""
    smoke_text = ""
    if CI_WORKFLOW.exists():
        ci_text = CI_WORKFLOW.read_text(encoding="utf-8")
    if SMOKE_WORKFLOW.exists():
        smoke_text = SMOKE_WORKFLOW.read_text(encoding="utf-8")

    checks.append(
        _check(
            "policy-bundle-governance:" in ci_text,
            "ci_policy_bundle_governance_job",
            "policy-bundle-governance job present",
        )
    )
    checks.append(
        _check(
            "python tooling/verify_policy_bundle_lifecycle.py" in ci_text,
            "ci_runs_policy_bundle_lifecycle_verifier",
            "verify_policy_bundle_lifecycle.py command present",
        )
    )
    checks.append(
        _check(
            "python tooling/verify_policy_gate_freshness.py" in ci_text,
            "ci_runs_policy_gate_freshness_verifier",
            "verify_policy_gate_freshness.py command present",
        )
    )
    checks.append(
        _check(
            "policy-bundle-governance-report" in ci_text,
            "ci_uploads_policy_bundle_governance_artifact",
            "policy-bundle-governance-report artifact present",
        )
    )

    checks.append(
        _check(
            "runtime_canary:" in smoke_text,
            "smoke_runtime_canary_job",
            "runtime_canary job present",
        )
    )
    checks.append(
        _check(
            "python tooling/verify_policy_bundle_lifecycle.py" in smoke_text,
            "smoke_runs_policy_bundle_lifecycle_verifier",
            "verify_policy_bundle_lifecycle.py command present",
        )
    )
    checks.append(
        _check(
            "artifacts/policy_bundle_lifecycle_report.json" in smoke_text,
            "smoke_publishes_policy_bundle_report",
            "policy bundle lifecycle report path referenced",
        )
    )

    passed = sum(1 for c in checks if c.get("passed") is True)
    total = len(checks)
    failed = total - passed
    pass_ratio = (passed / total) if total else 0.0

    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "status": "passed" if failed == 0 else "failed",
        "contract": "policy_gate_freshness_v1",
        "summary": {
            "total": total,
            "passed": passed,
            "failed": failed,
            "pass_ratio": pass_ratio,
        },
        "checks": checks,
    }

    args.report_file.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("Policy gate freshness summary")
    print(f"- passed: {passed}/{total}")
    print(f"- pass_ratio: {pass_ratio:.3f}")
    print(f"- report: {args.report_file}")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

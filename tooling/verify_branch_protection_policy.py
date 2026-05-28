#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
SMOKE_WORKFLOW = ROOT / ".github" / "workflows" / "smoke.yml"
POLICY_DOC = ROOT / "docs" / "BRANCH_PROTECTION_POLICY.md"
REQUIRED_CHECKS_FILE = ROOT / "docs" / "required_status_checks.json"
DEFAULT_REPORT = ROOT / "artifacts" / "branch_protection_policy_report.json"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify branch protection policy documentation and workflow alignment."
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

    checks.append(_check(POLICY_DOC.exists(), "policy_doc_exists", str(POLICY_DOC)))
    checks.append(
        _check(
            REQUIRED_CHECKS_FILE.exists(),
            "required_checks_file_exists",
            str(REQUIRED_CHECKS_FILE),
        )
    )
    checks.append(_check(CI_WORKFLOW.exists(), "ci_workflow_exists", str(CI_WORKFLOW)))
    checks.append(
        _check(SMOKE_WORKFLOW.exists(), "smoke_workflow_exists", str(SMOKE_WORKFLOW))
    )

    policy_text = POLICY_DOC.read_text(encoding="utf-8") if POLICY_DOC.exists() else ""
    ci_text = CI_WORKFLOW.read_text(encoding="utf-8") if CI_WORKFLOW.exists() else ""
    smoke_text = (
        SMOKE_WORKFLOW.read_text(encoding="utf-8") if SMOKE_WORKFLOW.exists() else ""
    )

    required_checks: list[str] = []
    if REQUIRED_CHECKS_FILE.exists():
        try:
            data = json.loads(REQUIRED_CHECKS_FILE.read_text(encoding="utf-8"))
            checks.append(_check(True, "required_checks_file_json_valid", "valid json"))
            raw_checks = data.get("required_status_checks")
            if isinstance(raw_checks, list):
                required_checks = [c for c in raw_checks if isinstance(c, str)]
        except Exception as exc:
            checks.append(
                _check(False, "required_checks_file_json_valid", f"invalid json: {exc}")
            )

    checks.append(
        _check(
            bool(required_checks),
            "required_checks_non_empty",
            f"count={len(required_checks)}",
        )
    )

    required_policy_tokens = [
        "Require pull request before merging",
        "Require status checks to pass before merging",
    ]
    required_policy_tokens.extend(required_checks)
    for token in required_policy_tokens:
        checks.append(
            _check(
                token in policy_text,
                f"policy_doc_token:{token}",
                token,
            )
        )

    checks.append(
        _check(
            "cognitive-quality-gates:" in ci_text,
            "ci_job_cognitive_quality_gates_present",
            "cognitive-quality-gates job present",
        )
    )
    checks.append(
        _check(
            "policy-bundle-governance:" in ci_text,
            "ci_job_policy_bundle_governance_present",
            "policy-bundle-governance job present",
        )
    )
    checks.append(
        _check(
            "runtime_canary:" in smoke_text,
            "smoke_job_runtime_canary_present",
            "runtime_canary job present",
        )
    )

    passed = sum(1 for c in checks if c.get("passed") is True)
    total = len(checks)
    failed = total - passed
    pass_ratio = (passed / total) if total else 0.0

    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "status": "passed" if failed == 0 else "failed",
        "contract": "branch_protection_policy_v1",
        "summary": {
            "total": total,
            "passed": passed,
            "failed": failed,
            "pass_ratio": pass_ratio,
        },
        "checks": checks,
    }

    args.report_file.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("Branch protection policy summary")
    print(f"- passed: {passed}/{total}")
    print(f"- pass_ratio: {pass_ratio:.3f}")
    print(f"- report: {args.report_file}")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

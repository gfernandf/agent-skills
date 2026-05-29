#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REPORT_FILE = ROOT / "artifacts" / "policy_promotion_readiness_report.json"
DEFAULT_VERIFY_REPORT = (
    ROOT / "artifacts" / "policy_promotion_readiness_verify_report.json"
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify policy promotion readiness report contract and status."
    )
    parser.add_argument(
        "--report-file",
        type=Path,
        default=DEFAULT_REPORT_FILE,
        help="Path to policy promotion readiness report.",
    )
    parser.add_argument(
        "--verify-report-file",
        type=Path,
        default=DEFAULT_VERIFY_REPORT,
        help="Path to write verification report.",
    )
    parser.add_argument(
        "--require-passed",
        action="store_true",
        help="Fail when report status is not passed.",
    )
    parser.add_argument(
        "--require-dev-to-staging-ready",
        action="store_true",
        help="Fail when environments.dev_to_staging.ready is not true.",
    )
    parser.add_argument(
        "--require-staging-to-prod-automated-ready",
        action="store_true",
        help="Fail when environments.staging_to_prod.automated_ready is not true.",
    )
    return parser.parse_args()


def _check(condition: bool, check_id: str, detail: str) -> dict[str, object]:
    return {"check_id": check_id, "passed": condition, "detail": detail}


def main() -> int:
    args = _parse_args()
    args.verify_report_file.parent.mkdir(parents=True, exist_ok=True)

    checks: list[dict[str, object]] = []

    checks.append(
        _check(args.report_file.exists(), "report_exists", str(args.report_file))
    )
    report: dict[str, object] = {}
    if args.report_file.exists():
        try:
            report = json.loads(args.report_file.read_text(encoding="utf-8"))
            checks.append(_check(True, "report_json_valid", "valid json"))
        except Exception as exc:
            checks.append(_check(False, "report_json_valid", f"invalid json: {exc}"))

    status = str(report.get("status", "")).lower() if report else ""
    contract = report.get("contract") if report else None
    summary = (
        report.get("summary", {}) if isinstance(report.get("summary"), dict) else {}
    )
    environments = (
        report.get("environments", {})
        if isinstance(report.get("environments"), dict)
        else {}
    )
    dev_to_staging = (
        environments.get("dev_to_staging", {})
        if isinstance(environments.get("dev_to_staging"), dict)
        else {}
    )
    staging_to_prod = (
        environments.get("staging_to_prod", {})
        if isinstance(environments.get("staging_to_prod"), dict)
        else {}
    )

    checks.append(
        _check(
            contract == "policy_promotion_readiness_v1",
            "report_contract",
            str(contract),
        )
    )
    checks.append(
        _check(
            isinstance(summary.get("runtime_canary_pass_ratio"), (int, float)),
            "summary_runtime_canary_pass_ratio_present",
            str(summary.get("runtime_canary_pass_ratio")),
        )
    )
    checks.append(
        _check(
            isinstance(dev_to_staging.get("ready"), bool),
            "environments_dev_to_staging_ready_present",
            str(dev_to_staging.get("ready")),
        )
    )
    checks.append(
        _check(
            isinstance(staging_to_prod.get("automated_ready"), bool),
            "environments_staging_to_prod_automated_ready_present",
            str(staging_to_prod.get("automated_ready")),
        )
    )

    if args.require_passed:
        checks.append(_check(status == "passed", "require_status_passed", status))
    if args.require_dev_to_staging_ready:
        checks.append(
            _check(
                dev_to_staging.get("ready") is True,
                "require_dev_to_staging_ready",
                str(dev_to_staging.get("ready")),
            )
        )
    if args.require_staging_to_prod_automated_ready:
        checks.append(
            _check(
                staging_to_prod.get("automated_ready") is True,
                "require_staging_to_prod_automated_ready",
                str(staging_to_prod.get("automated_ready")),
            )
        )

    passed = sum(1 for c in checks if c.get("passed") is True)
    total = len(checks)
    failed = total - passed
    pass_ratio = (passed / total) if total else 0.0

    verify_report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "status": "passed" if failed == 0 else "failed",
        "contract": "policy_promotion_readiness_verify_v1",
        "input_report": str(args.report_file),
        "summary": {
            "total": total,
            "passed": passed,
            "failed": failed,
            "pass_ratio": pass_ratio,
        },
        "checks": checks,
    }

    args.verify_report_file.write_text(
        json.dumps(verify_report, indent=2),
        encoding="utf-8",
    )

    print("Policy promotion readiness verify summary")
    print(f"- passed: {passed}/{total}")
    print(f"- pass_ratio: {pass_ratio:.3f}")
    print(f"- report: {args.verify_report_file}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

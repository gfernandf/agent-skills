#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REPORT_FILE = ROOT / "artifacts" / "release_readiness_gate_report.json"
DEFAULT_MARKDOWN_FILE = ROOT / "artifacts" / "release_readiness_gate_summary.md"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate release readiness Go/No-Go gate from workflow job results and artifacts."
    )
    parser.add_argument(
        "--needs-json",
        default="{}",
        help="JSON object from GitHub Actions needs context (for example: ${{ toJson(needs) }}).",
    )
    parser.add_argument(
        "--artifacts-dir",
        type=Path,
        default=ROOT / "artifacts",
        help="Directory containing downloaded artifacts.",
    )
    parser.add_argument(
        "--report-file",
        type=Path,
        default=DEFAULT_REPORT_FILE,
        help="Path to write the gate report JSON.",
    )
    parser.add_argument(
        "--markdown-file",
        type=Path,
        default=DEFAULT_MARKDOWN_FILE,
        help="Path to write markdown summary.",
    )
    parser.add_argument(
        "--allow-trend-unverified",
        action="store_true",
        help="Allow critical trend SLO status=unverified without failing the gate.",
    )
    parser.add_argument(
        "--allow-missing-runtime-executive-summary",
        action="store_true",
        help="Treat missing runtime governance executive summary as warning instead of failure.",
    )
    parser.add_argument(
        "--fail-on-no-go",
        action="store_true",
        help="Exit non-zero when final decision is no-go.",
    )
    return parser.parse_args()


def _load_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not path.exists():
        return None, "missing"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return None, f"invalid_json: {exc}"
    if not isinstance(payload, dict):
        return None, "invalid_shape"
    return payload, None


def _append_check(
    checks: list[dict[str, Any]],
    *,
    check_id: str,
    passed: bool,
    severity: str,
    detail: str,
) -> None:
    checks.append(
        {
            "check_id": check_id,
            "passed": passed,
            "severity": severity,
            "detail": detail,
        }
    )


def _status_is_pass(value: Any) -> bool:
    return isinstance(value, str) and value.strip().lower() in {"pass", "passed", "ok", "success"}


def main() -> int:
    args = _parse_args()
    args.report_file.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_file.parent.mkdir(parents=True, exist_ok=True)

    checks: list[dict[str, Any]] = []

    try:
        needs = json.loads(args.needs_json)
    except Exception as exc:
        needs = {}
        _append_check(
            checks,
            check_id="needs_json_parse",
            passed=False,
            severity="high",
            detail=f"needs_json parse failed: {exc}",
        )
    else:
        _append_check(
            checks,
            check_id="needs_json_parse",
            passed=isinstance(needs, dict),
            severity="high",
            detail="parsed" if isinstance(needs, dict) else "not an object",
        )

    required_jobs = [
        "pin_drift_guard",
        "smoke",
        "contracts",
        "registry_consistency",
        "openapi_verification",
        "runtime_canary",
        "dx_metrics",
        "ci_stability_trend",
    ]

    for job in required_jobs:
        item = needs.get(job) if isinstance(needs, dict) else None
        result = item.get("result") if isinstance(item, dict) else None
        _append_check(
            checks,
            check_id=f"job_result:{job}",
            passed=result == "success",
            severity="high",
            detail=f"result={result}",
        )

    artifacts_dir = args.artifacts_dir

    smoke_data, smoke_error = _load_json(artifacts_dir / "smoke_report.json")
    if smoke_error:
        _append_check(
            checks,
            check_id="smoke_report_present",
            passed=False,
            severity="high",
            detail=smoke_error,
        )
    else:
        failed = smoke_data.get("failed")
        _append_check(
            checks,
            check_id="smoke_report_failed_zero",
            passed=isinstance(failed, int) and failed == 0,
            severity="high",
            detail=f"failed={failed}",
        )

    promo_verify_data, promo_verify_error = _load_json(
        artifacts_dir / "policy_promotion_readiness_verify_report.json"
    )
    if promo_verify_error:
        _append_check(
            checks,
            check_id="promotion_verify_report_present",
            passed=False,
            severity="high",
            detail=promo_verify_error,
        )
    else:
        status = promo_verify_data.get("status")
        _append_check(
            checks,
            check_id="promotion_verify_status_passed",
            passed=_status_is_pass(status),
            severity="high",
            detail=f"status={status}",
        )

    runtime_exec_data, runtime_exec_error = _load_json(
        artifacts_dir / "runtime_governance_executive_summary.json"
    )
    if runtime_exec_error:
        _append_check(
            checks,
            check_id="runtime_exec_summary_present",
            passed=args.allow_missing_runtime_executive_summary,
            severity="medium" if args.allow_missing_runtime_executive_summary else "high",
            detail=runtime_exec_error,
        )
    else:
        status = runtime_exec_data.get("status")
        _append_check(
            checks,
            check_id="runtime_exec_summary_not_failed",
            passed=str(status).strip().lower() != "failed",
            severity="high",
            detail=f"status={status}",
        )

    dx_slo_data, dx_slo_error = _load_json(artifacts_dir / "dx_metrics_slo_report.json")
    if dx_slo_error:
        _append_check(
            checks,
            check_id="dx_slo_report_present",
            passed=False,
            severity="high",
            detail=dx_slo_error,
        )
    else:
        slo_status = dx_slo_data.get("slo_status")
        _append_check(
            checks,
            check_id="dx_slo_status_pass",
            passed=_status_is_pass(slo_status),
            severity="high",
            detail=f"slo_status={slo_status}",
        )

    trend_slo_data, trend_slo_error = _load_json(artifacts_dir / "critical_ci_trend_slo_report.json")
    if trend_slo_error:
        _append_check(
            checks,
            check_id="trend_slo_report_present",
            passed=False,
            severity="high",
            detail=trend_slo_error,
        )
    else:
        trend_slo_status = str(trend_slo_data.get("slo_status", "unknown")).strip().lower()
        trend_ok = trend_slo_status in {"pass", "passed"}
        trend_allowed = args.allow_trend_unverified and trend_slo_status == "unverified"
        _append_check(
            checks,
            check_id="trend_slo_status",
            passed=trend_ok or trend_allowed,
            severity="medium" if trend_allowed else "high",
            detail=f"slo_status={trend_slo_status}",
        )

    high_failures = [c for c in checks if not c.get("passed") and c.get("severity") == "high"]
    medium_failures = [c for c in checks if not c.get("passed") and c.get("severity") == "medium"]

    if high_failures:
        decision = "no-go"
    elif medium_failures:
        decision = "conditional-go"
    else:
        decision = "go"

    summary = {
        "total": len(checks),
        "passed": sum(1 for c in checks if c.get("passed")),
        "failed": sum(1 for c in checks if not c.get("passed")),
        "high_failures": len(high_failures),
        "medium_failures": len(medium_failures),
    }

    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "status": "passed" if decision == "go" else "failed",
        "contract": "release_readiness_gate_v1",
        "decision": decision,
        "summary": summary,
        "checks": checks,
        "inputs": {
            "artifacts_dir": str(artifacts_dir),
            "allow_trend_unverified": args.allow_trend_unverified,
            "allow_missing_runtime_executive_summary": args.allow_missing_runtime_executive_summary,
        },
    }

    args.report_file.write_text(json.dumps(report, indent=2), encoding="utf-8")

    lines = [
        "## Release Readiness Gate",
        "",
        f"- Decision: {decision}",
        f"- Status: {report['status']}",
        f"- Passed checks: {summary['passed']}/{summary['total']}",
        f"- High failures: {summary['high_failures']}",
        f"- Medium failures: {summary['medium_failures']}",
        "",
    ]

    if high_failures or medium_failures:
        lines.append("### Failing Checks")
        lines.append("")
        for item in [*high_failures, *medium_failures]:
            lines.append(
                f"- [{item.get('severity')}] {item.get('check_id')}: {item.get('detail')}"
            )
    else:
        lines.append("All release readiness checks passed.")

    lines.append("")
    args.markdown_file.write_text("\n".join(lines), encoding="utf-8")

    print("Release readiness gate")
    print(f"- decision: {decision}")
    print(f"- status: {report['status']}")
    print(f"- passed: {summary['passed']}/{summary['total']}")
    print(f"- high_failures: {summary['high_failures']}")
    print(f"- medium_failures: {summary['medium_failures']}")
    print(f"- report: {args.report_file}")
    print(f"- markdown: {args.markdown_file}")

    if args.fail_on_no_go and decision == "no-go":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

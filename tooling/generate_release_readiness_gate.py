#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
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
    parser.add_argument(
        "--exceptions-file",
        type=Path,
        default=None,
        help=(
            "Optional JSON file with temporary approved exceptions. "
            "Format: {\"exceptions\": [{\"check_id\":...,\"expires_at\":...,\"approved_by\":...,\"reason\":...}]}"
        ),
    )
    parser.add_argument(
        "--policy-file",
        type=Path,
        default=None,
        help="Optional JSON policy file for release gate behavior and thresholds.",
    )
    parser.add_argument(
        "--policy-profile",
        default="strict",
        help="Policy profile name from policy file (for example: strict, transitional).",
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


def _parse_utc(value: str) -> datetime | None:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _load_active_exceptions(path: Path | None) -> tuple[dict[str, dict[str, str]], list[str], str | None]:
    if path is None:
        return {}, [], None
    if not path.exists():
        return {}, [], f"exceptions file missing: {path}"

    data, error = _load_json(path)
    if error:
        return {}, [], f"exceptions file error: {error}"

    raw_items = data.get("exceptions") if isinstance(data, dict) else None
    if not isinstance(raw_items, list):
        return {}, [], "exceptions file invalid: exceptions must be a list"

    active: dict[str, dict[str, str]] = {}
    issues: list[str] = []
    now = datetime.now(timezone.utc)

    for idx, item in enumerate(raw_items):
        if not isinstance(item, dict):
            issues.append(f"exceptions[{idx}] invalid: not object")
            continue

        check_id = item.get("check_id")
        expires_at = item.get("expires_at")
        approved_by = item.get("approved_by")
        reason = item.get("reason")

        if not isinstance(check_id, str) or not check_id.strip():
            issues.append(f"exceptions[{idx}] invalid: check_id")
            continue
        if not isinstance(expires_at, str) or not expires_at.strip():
            issues.append(f"exceptions[{idx}] invalid: expires_at")
            continue
        if not isinstance(approved_by, str) or not approved_by.strip():
            issues.append(f"exceptions[{idx}] invalid: approved_by")
            continue
        if not isinstance(reason, str) or not reason.strip():
            issues.append(f"exceptions[{idx}] invalid: reason")
            continue

        expires_dt = _parse_utc(expires_at)
        if expires_dt is None:
            issues.append(f"exceptions[{idx}] invalid datetime: {expires_at}")
            continue
        if expires_dt <= now:
            issues.append(f"exceptions[{idx}] expired: {check_id} at {expires_at}")
            continue

        active[check_id] = {
            "approved_by": approved_by.strip(),
            "reason": reason.strip(),
            "expires_at": expires_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    return active, issues, None


def _load_policy(path: Path | None, profile: str) -> tuple[dict[str, Any], str | None]:
    default_policy = {
        "allow_trend_unverified": False,
        "allow_missing_runtime_executive_summary": False,
        "max_high_failures": 0,
        "max_medium_failures": 0,
        "dx_allowed_slo_statuses": ["pass", "passed"],
        "trend_allowed_slo_statuses": ["pass", "passed"],
    }
    if path is None:
        return default_policy, None
    data, error = _load_json(path)
    if error:
        return default_policy, f"policy file error: {error}"
    profiles = data.get("profiles") if isinstance(data, dict) else None
    if not isinstance(profiles, dict):
        return default_policy, "policy file invalid: profiles must be an object"
    selected = profiles.get(profile)
    if not isinstance(selected, dict):
        return default_policy, f"policy profile not found: {profile}"

    resolved = dict(default_policy)
    resolved.update(selected)
    return resolved, None


def main() -> int:
    args = _parse_args()
    args.report_file.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_file.parent.mkdir(parents=True, exist_ok=True)

    checks: list[dict[str, Any]] = []
    exceptions_applied: list[dict[str, str]] = []

    policy, policy_error = _load_policy(args.policy_file, args.policy_profile)
    if policy_error is not None:
        _append_check(
            checks,
            check_id="policy_load",
            passed=False,
            severity="high",
            detail=policy_error,
        )
    elif args.policy_file is not None:
        _append_check(
            checks,
            check_id="policy_load",
            passed=True,
            severity="high",
            detail=f"loaded profile={args.policy_profile} from {args.policy_file}",
        )

    allow_trend_unverified = bool(policy.get("allow_trend_unverified", args.allow_trend_unverified))
    allow_missing_runtime_exec_summary = bool(
        policy.get(
            "allow_missing_runtime_executive_summary",
            args.allow_missing_runtime_executive_summary,
        )
    )
    max_high_failures = int(policy.get("max_high_failures", 0))
    max_medium_failures = int(policy.get("max_medium_failures", 0))

    dx_allowed_slo_statuses_raw = policy.get("dx_allowed_slo_statuses", ["pass", "passed"])
    if not isinstance(dx_allowed_slo_statuses_raw, list):
        dx_allowed_slo_statuses_raw = ["pass", "passed"]
    dx_allowed_slo_statuses = {
        str(item).strip().lower() for item in dx_allowed_slo_statuses_raw if str(item).strip()
    }

    trend_allowed_slo_statuses_raw = policy.get("trend_allowed_slo_statuses", ["pass", "passed"])
    if not isinstance(trend_allowed_slo_statuses_raw, list):
        trend_allowed_slo_statuses_raw = ["pass", "passed"]
    trend_allowed_slo_statuses = {
        str(item).strip().lower() for item in trend_allowed_slo_statuses_raw if str(item).strip()
    }

    active_exceptions, exception_issues, exceptions_load_error = _load_active_exceptions(
        args.exceptions_file
    )
    if exceptions_load_error is not None:
        _append_check(
            checks,
            check_id="exceptions_file_load",
            passed=False,
            severity="high",
            detail=exceptions_load_error,
        )
    elif args.exceptions_file is not None:
        _append_check(
            checks,
            check_id="exceptions_file_load",
            passed=True,
            severity="high",
            detail=f"loaded from {args.exceptions_file}",
        )

    for issue in exception_issues:
        _append_check(
            checks,
            check_id="exceptions_entry_issue",
            passed=False,
            severity="medium",
            detail=issue,
        )

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

    runtime_coverage_data, runtime_coverage_error = _load_json(
        artifacts_dir / "runtime_coverage.json"
    )
    if runtime_coverage_error:
        _append_check(
            checks,
            check_id="runtime_coverage_report_present",
            passed=False,
            severity="high",
            detail=runtime_coverage_error,
        )
    else:
        ratio = runtime_coverage_data.get("coverage_ratio")
        ratio_value = float(ratio) if isinstance(ratio, (int, float)) else -1.0
        _append_check(
            checks,
            check_id="runtime_coverage_ratio",
            passed=ratio_value >= 1.0,
            severity="high",
            detail=f"coverage_ratio={ratio}",
        )

    executability_data, executability_error = _load_json(
        artifacts_dir / "skill_executability.json"
    )
    if executability_error:
        _append_check(
            checks,
            check_id="skill_executability_report_present",
            passed=False,
            severity="high",
            detail=executability_error,
        )
    else:
        ratio = executability_data.get("executability_ratio")
        ratio_value = float(ratio) if isinstance(ratio, (int, float)) else -1.0
        _append_check(
            checks,
            check_id="skill_executability_ratio",
            passed=ratio_value >= 1.0,
            severity="high",
            detail=f"executability_ratio={ratio}",
        )

    lifecycle_data, lifecycle_error = _load_json(
        artifacts_dir / "policy_bundle_lifecycle_report.json"
    )
    if lifecycle_error:
        _append_check(
            checks,
            check_id="policy_bundle_lifecycle_report_present",
            passed=False,
            severity="high",
            detail=lifecycle_error,
        )
    else:
        status = lifecycle_data.get("status")
        _append_check(
            checks,
            check_id="policy_bundle_lifecycle_status_passed",
            passed=_status_is_pass(status),
            severity="high",
            detail=f"status={status}",
        )

    promotion_data, promotion_error = _load_json(
        artifacts_dir / "policy_promotion_readiness_report.json"
    )
    if promotion_error:
        _append_check(
            checks,
            check_id="promotion_readiness_report_present",
            passed=False,
            severity="high",
            detail=promotion_error,
        )
    else:
        status = promotion_data.get("status")
        _append_check(
            checks,
            check_id="promotion_readiness_status_passed",
            passed=_status_is_pass(status),
            severity="high",
            detail=f"status={status}",
        )

    durability_advanced_data, durability_advanced_error = _load_json(
        artifacts_dir / "durability_advanced_report.json"
    )
    if durability_advanced_error:
        _append_check(
            checks,
            check_id="durability_advanced_report_present",
            passed=False,
            severity="high",
            detail=durability_advanced_error,
        )
    else:
        status = durability_advanced_data.get("status")
        _append_check(
            checks,
            check_id="durability_advanced_status_passed",
            passed=_status_is_pass(status),
            severity="high",
            detail=f"status={status}",
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
            passed=allow_missing_runtime_exec_summary,
            severity="medium" if allow_missing_runtime_exec_summary else "high",
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
        normalized_dx_status = str(slo_status).strip().lower()
        _append_check(
            checks,
            check_id="dx_slo_status_pass",
            passed=normalized_dx_status in dx_allowed_slo_statuses,
            severity="high",
            detail=f"slo_status={slo_status}; allowed={sorted(dx_allowed_slo_statuses)}",
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
        trend_ok = trend_slo_status in trend_allowed_slo_statuses
        trend_allowed = allow_trend_unverified and trend_slo_status == "unverified"
        _append_check(
            checks,
            check_id="trend_slo_status",
            passed=trend_ok or trend_allowed,
            severity="medium" if trend_allowed else "high",
            detail=f"slo_status={trend_slo_status}; allowed={sorted(trend_allowed_slo_statuses)}",
        )

    trend_data, trend_error = _load_json(artifacts_dir / "critical_ci_trend_report.json")
    if trend_error:
        _append_check(
            checks,
            check_id="trend_report_present",
            passed=False,
            severity="high",
            detail=trend_error,
        )
    else:
        status = str(trend_data.get("status", "unknown")).strip().lower()
        status_ok = status == "passed"
        status_allowed = allow_trend_unverified and status == "unverified"
        _append_check(
            checks,
            check_id="trend_report_status",
            passed=status_ok or status_allowed,
            severity="medium" if status_allowed else "high",
            detail=f"status={status}",
        )

    high_failures = [c for c in checks if not c.get("passed") and c.get("severity") == "high"]
    medium_failures = [c for c in checks if not c.get("passed") and c.get("severity") == "medium"]

    for check in checks:
        if check.get("passed"):
            continue
        check_id = str(check.get("check_id", "")).strip()
        exception = active_exceptions.get(check_id)
        if not exception:
            continue
        if check.get("severity") == "high":
            check["severity"] = "medium"
        check["detail"] = (
            f"{check.get('detail')} | exception approved_by={exception['approved_by']} "
            f"expires_at={exception['expires_at']} reason={exception['reason']}"
        )
        exceptions_applied.append(
            {
                "check_id": check_id,
                "approved_by": exception["approved_by"],
                "expires_at": exception["expires_at"],
                "reason": exception["reason"],
            }
        )

    high_failures = [c for c in checks if not c.get("passed") and c.get("severity") == "high"]
    medium_failures = [c for c in checks if not c.get("passed") and c.get("severity") == "medium"]

    if len(high_failures) > max_high_failures:
        decision = "no-go"
    elif len(medium_failures) > max_medium_failures:
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
            "allow_trend_unverified": allow_trend_unverified,
            "allow_missing_runtime_executive_summary": allow_missing_runtime_exec_summary,
            "exceptions_file": str(args.exceptions_file) if args.exceptions_file else None,
            "policy_file": str(args.policy_file) if args.policy_file else None,
            "policy_profile": args.policy_profile,
            "max_high_failures": max_high_failures,
            "max_medium_failures": max_medium_failures,
            "dx_allowed_slo_statuses": sorted(dx_allowed_slo_statuses),
            "trend_allowed_slo_statuses": sorted(trend_allowed_slo_statuses),
        },
        "exceptions_applied": exceptions_applied,
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
        f"- Exceptions applied: {len(exceptions_applied)}",
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

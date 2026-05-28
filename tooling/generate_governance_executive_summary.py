#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REPORT_FILE = ROOT / "artifacts" / "governance_executive_summary.json"
DEFAULT_MARKDOWN_FILE = ROOT / "artifacts" / "governance_executive_summary.md"
DEFAULT_INPUT_REPORTS = [
    ROOT / "artifacts" / "policy_bundle_lifecycle_report.json",
    ROOT / "artifacts" / "policy_gate_freshness_report.json",
    ROOT / "artifacts" / "branch_protection_policy_report.json",
    ROOT / "artifacts" / "required_status_checks_consistency_report.json",
    ROOT / "artifacts" / "github_branch_protection_report.json",
    ROOT / "artifacts" / "workflow_embedded_python_report.json",
    ROOT / "artifacts" / "policy_promotion_readiness_report.json",
    ROOT / "artifacts" / "policy_promotion_readiness_verify_report.json",
    ROOT / "artifacts" / "critical_ci_trend_report.json",
    ROOT / "artifacts" / "critical_ci_trend_slo_report.json",
    ROOT / "artifacts" / "dx_metrics_slo_report.json",
]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a single governance executive summary from one or more JSON "
            "governance reports."
        )
    )
    parser.add_argument(
        "--input-report",
        action="append",
        dest="input_reports",
        default=None,
        help=(
            "Path to an input governance report JSON. "
            "Can be supplied multiple times."
        ),
    )
    parser.add_argument(
        "--report-file",
        type=Path,
        default=DEFAULT_REPORT_FILE,
        help="Path to write consolidated summary JSON.",
    )
    parser.add_argument(
        "--markdown-file",
        type=Path,
        default=DEFAULT_MARKDOWN_FILE,
        help="Path to write consolidated summary markdown.",
    )
    parser.add_argument(
        "--title",
        default="Governance Executive Summary",
        help="Title used in markdown output.",
    )
    parser.add_argument(
        "--fail-on-failed",
        action="store_true",
        help="Exit with non-zero code when consolidated status is failed.",
    )
    return parser.parse_args()


def _canonical_status(report: dict[str, Any]) -> str:
    candidate = report.get("status")
    if not isinstance(candidate, str) and isinstance(report.get("slo_status"), str):
        candidate = report.get("slo_status")

    normalized = (candidate or "unknown").strip().lower()

    if normalized in {"passed", "pass", "ok", "healthy", "success"}:
        return "passed"
    if normalized in {"failed", "fail", "error", "breach"}:
        return "failed"
    if normalized in {"unverified", "unknown", "pending", "partial", "warning"}:
        return "unverified"
    return "unknown"


def _build_summary_line(report: dict[str, Any]) -> str:
    summary = report.get("summary")
    if isinstance(summary, dict):
        passed = summary.get("passed")
        total = summary.get("total")
        failed = summary.get("failed")
        pass_ratio = summary.get("pass_ratio")
        details: list[str] = []
        if passed is not None and total is not None:
            details.append(f"passed={passed}/{total}")
        if failed is not None:
            details.append(f"failed={failed}")
        if pass_ratio is not None:
            details.append(f"pass_ratio={pass_ratio}")
        if details:
            return ", ".join(details)

    breaches = report.get("breaches")
    warnings = report.get("warnings")
    if isinstance(breaches, list) or isinstance(warnings, list):
        return f"breaches={len(breaches or [])}, warnings={len(warnings or [])}"

    return "no structured summary"


def _load_report(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not path.exists():
        return None, "missing"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - exercised in CI runs on failures
        return None, f"invalid_json: {exc}"
    if not isinstance(data, dict):
        return None, "invalid_shape: top-level value is not object"
    return data, None


def main() -> int:
    args = _parse_args()

    input_paths = (
        [Path(item) for item in args.input_reports]
        if args.input_reports
        else list(DEFAULT_INPUT_REPORTS)
    )

    args.report_file.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_file.parent.mkdir(parents=True, exist_ok=True)

    report_entries: list[dict[str, Any]] = []
    counts = {
        "passed": 0,
        "failed": 0,
        "unverified": 0,
        "unknown": 0,
        "invalid": 0,
        "missing": 0,
    }

    for path in input_paths:
        data, error = _load_report(path)
        if error == "missing":
            counts["missing"] += 1
            report_entries.append(
                {
                    "path": str(path),
                    "status": "missing",
                    "contract": None,
                    "detail": "report not found",
                    "summary": "missing",
                }
            )
            continue
        if error is not None:
            counts["invalid"] += 1
            report_entries.append(
                {
                    "path": str(path),
                    "status": "invalid",
                    "contract": None,
                    "detail": error,
                    "summary": "invalid",
                }
            )
            continue

        assert data is not None
        status = _canonical_status(data)
        if status not in counts:
            status = "unknown"
        counts[status] += 1

        report_entries.append(
            {
                "path": str(path),
                "status": status,
                "contract": data.get("contract"),
                "detail": data.get("status") or data.get("slo_status") or "unknown",
                "summary": _build_summary_line(data),
            }
        )

    if counts["failed"] > 0 or counts["invalid"] > 0:
        overall_status = "failed"
    elif counts["unverified"] > 0 or counts["unknown"] > 0 or counts["missing"] > 0:
        overall_status = "unverified"
    else:
        overall_status = "passed"

    output = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "status": overall_status,
        "contract": "governance_executive_summary_v1",
        "summary": {
            "total_reports": len(report_entries),
            "passed": counts["passed"],
            "failed": counts["failed"],
            "unverified": counts["unverified"],
            "unknown": counts["unknown"],
            "invalid": counts["invalid"],
            "missing": counts["missing"],
        },
        "reports": report_entries,
    }

    args.report_file.write_text(json.dumps(output, indent=2), encoding="utf-8")

    lines = [f"## {args.title}", ""]
    lines.append(f"- Overall status: {overall_status}")
    lines.append(f"- Total reports: {len(report_entries)}")
    lines.append(f"- Passed: {counts['passed']}")
    lines.append(f"- Failed: {counts['failed']}")
    lines.append(f"- Unverified: {counts['unverified']}")
    lines.append(f"- Unknown: {counts['unknown']}")
    lines.append(f"- Invalid: {counts['invalid']}")
    lines.append(f"- Missing: {counts['missing']}")
    lines.append("")
    lines.append("### Inputs")
    lines.append("")

    for item in report_entries:
        path = item.get("path", "<unknown>")
        status = item.get("status", "unknown")
        contract = item.get("contract") or "n/a"
        detail = item.get("detail") or "n/a"
        summary_line = item.get("summary") or "n/a"
        lines.append(
            f"- {path}: status={status}, contract={contract}, detail={detail}; {summary_line}"
        )

    lines.append("")
    args.markdown_file.write_text("\n".join(lines), encoding="utf-8")

    print("Governance executive summary")
    print(f"- status: {overall_status}")
    print(f"- total_reports: {len(report_entries)}")
    print(f"- passed: {counts['passed']}")
    print(f"- failed: {counts['failed']}")
    print(f"- unverified: {counts['unverified']}")
    print(f"- invalid: {counts['invalid']}")
    print(f"- missing: {counts['missing']}")
    print(f"- report: {args.report_file}")
    print(f"- markdown: {args.markdown_file}")

    if args.fail_on_failed and overall_status == "failed":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

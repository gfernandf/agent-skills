#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TREND_REPORT = ROOT / "artifacts" / "critical_ci_trend_report.json"
DEFAULT_SLO_REPORT = ROOT / "artifacts" / "critical_ci_trend_slo_report.json"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate critical CI trend report against configurable pass-rate SLO thresholds."
        )
    )
    parser.add_argument(
        "--trend-report-file",
        type=Path,
        default=DEFAULT_TREND_REPORT,
        help="Path to critical CI trend report JSON.",
    )
    parser.add_argument(
        "--slo-report-file",
        type=Path,
        default=DEFAULT_SLO_REPORT,
        help="Path to write SLO evaluation report.",
    )
    parser.add_argument(
        "--min-pass-rate",
        type=float,
        default=0.80,
        help="Minimum pass rate expected for each critical job.",
    )
    parser.add_argument(
        "--min-samples",
        type=int,
        default=5,
        help="Minimum samples required before enforcing pass-rate threshold.",
    )
    parser.add_argument(
        "--fail-on-breach",
        action="store_true",
        help="Exit with non-zero code if SLO breaches are found.",
    )
    parser.add_argument(
        "--fail-on-unverified",
        action="store_true",
        help="Exit with non-zero code if trend report status is unverified.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    args.slo_report_file.parent.mkdir(parents=True, exist_ok=True)

    if not args.trend_report_file.exists():
        report = {
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "status": "failed",
            "contract": "critical_ci_trend_slo_v1",
            "reason": f"trend report missing: {args.trend_report_file}",
        }
        args.slo_report_file.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(report["reason"])
        return 1

    trend_report = json.loads(args.trend_report_file.read_text(encoding="utf-8"))
    trend_status = str(trend_report.get("status", "unknown")).lower()
    jobs = trend_report.get("critical_jobs", {})
    jobs = jobs if isinstance(jobs, dict) else {}

    breaches: list[str] = []
    warnings: list[str] = []

    for job_name, data in jobs.items():
        if not isinstance(data, dict):
            warnings.append(f"{job_name}: invalid job data")
            continue

        samples = int(data.get("samples", 0) or 0)
        pass_rate = float(data.get("pass_rate", 0.0) or 0.0)

        if samples < args.min_samples:
            warnings.append(
                f"{job_name}: samples below threshold ({samples} < {args.min_samples})"
            )
            continue

        if pass_rate < args.min_pass_rate:
            breaches.append(
                f"{job_name}: pass_rate below threshold ({pass_rate:.3f} < {args.min_pass_rate:.3f})"
            )

    slo_status = "pass"
    if breaches:
        slo_status = "breach"
    elif trend_status == "unverified":
        slo_status = "unverified"

    slo_report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "status": "passed" if slo_status == "pass" else "failed",
        "contract": "critical_ci_trend_slo_v1",
        "trend_report_file": str(args.trend_report_file),
        "trend_status": trend_status,
        "slo_status": slo_status,
        "thresholds": {
            "min_pass_rate": args.min_pass_rate,
            "min_samples": args.min_samples,
        },
        "breaches": breaches,
        "warnings": warnings,
    }

    args.slo_report_file.write_text(json.dumps(slo_report, indent=2), encoding="utf-8")

    print("Critical CI trend SLO summary")
    print(f"- trend_status: {trend_status}")
    print(f"- slo_status: {slo_status}")
    print(f"- breaches: {len(breaches)}")
    print(f"- warnings: {len(warnings)}")
    print(f"- report: {args.slo_report_file}")

    if breaches and args.fail_on_breach:
        return 1
    if trend_status == "unverified" and args.fail_on_unverified:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

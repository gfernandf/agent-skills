#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate DX metrics report, append a trend history entry, and optionally enforce SLO thresholds."
        )
    )
    parser.add_argument(
        "--metrics-file",
        type=Path,
        default=ROOT / "artifacts" / "dx_metrics.json",
        help="Path to dx_metrics JSON report.",
    )
    parser.add_argument(
        "--history-file",
        type=Path,
        default=ROOT / "artifacts" / "dx_metrics_history.jsonl",
        help="Path to append history entries in JSONL format.",
    )
    parser.add_argument(
        "--slo-report-file",
        type=Path,
        default=ROOT / "artifacts" / "dx_metrics_slo_report.json",
        help="Path to write SLO evaluation report.",
    )
    parser.add_argument(
        "--max-time-to-first-success-seconds",
        type=float,
        default=None,
        help="Optional max threshold for time_to_first_success_seconds.",
    )
    parser.add_argument(
        "--min-docs-parity-score",
        type=float,
        default=None,
        help="Optional min threshold for docs_parity_score.",
    )
    parser.add_argument(
        "--min-check-pass-ratio",
        type=float,
        default=None,
        help="Optional min threshold for checks_passed/checks_total.",
    )
    parser.add_argument(
        "--fail-on-slo-breach",
        action="store_true",
        help="Exit with code 1 when any configured threshold is breached.",
    )
    return parser.parse_args()


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"DX metrics file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def main() -> int:
    args = _parse_args()

    report = _load_json(args.metrics_file)
    metrics = report.get("metrics", {}) if isinstance(report, dict) else {}

    ttfs = _safe_float(metrics.get("time_to_first_success_seconds"))
    docs_parity = _safe_float(metrics.get("docs_parity_score"))
    checks_total = _safe_float(metrics.get("checks_total"))
    checks_passed = _safe_float(metrics.get("checks_passed"))
    pass_ratio = None
    if checks_total and checks_total > 0 and checks_passed is not None:
        pass_ratio = checks_passed / checks_total

    entry = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "status": report.get("status", "unknown"),
        "time_to_first_success_seconds": ttfs,
        "docs_parity_score": docs_parity,
        "checks_total": checks_total,
        "checks_passed": checks_passed,
        "check_pass_ratio": pass_ratio,
    }

    args.history_file.parent.mkdir(parents=True, exist_ok=True)
    with args.history_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=True) + "\n")

    breaches: list[str] = []
    thresholds = {
        "max_time_to_first_success_seconds": args.max_time_to_first_success_seconds,
        "min_docs_parity_score": args.min_docs_parity_score,
        "min_check_pass_ratio": args.min_check_pass_ratio,
    }

    if (
        args.max_time_to_first_success_seconds is not None
        and ttfs is not None
        and ttfs > args.max_time_to_first_success_seconds
    ):
        breaches.append(
            "time_to_first_success_seconds exceeded: "
            f"{ttfs:.3f} > {args.max_time_to_first_success_seconds:.3f}"
        )

    if (
        args.min_docs_parity_score is not None
        and docs_parity is not None
        and docs_parity < args.min_docs_parity_score
    ):
        breaches.append(
            "docs_parity_score below threshold: "
            f"{docs_parity:.3f} < {args.min_docs_parity_score:.3f}"
        )

    if (
        args.min_check_pass_ratio is not None
        and pass_ratio is not None
        and pass_ratio < args.min_check_pass_ratio
    ):
        breaches.append(
            "check_pass_ratio below threshold: "
            f"{pass_ratio:.3f} < {args.min_check_pass_ratio:.3f}"
        )

    slo_report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "metrics_file": str(args.metrics_file),
        "history_file": str(args.history_file),
        "thresholds": thresholds,
        "current": entry,
        "breaches": breaches,
        "slo_status": "pass" if not breaches else "breach",
    }

    args.slo_report_file.parent.mkdir(parents=True, exist_ok=True)
    args.slo_report_file.write_text(json.dumps(slo_report, indent=2), encoding="utf-8")

    print("DX SLO evaluation")
    print(f"- metrics file: {args.metrics_file}")
    print(f"- history file: {args.history_file}")
    print(f"- slo report: {args.slo_report_file}")
    if breaches:
        print("- status: breach")
        for breach in breaches:
            print(f"  - {breach}")
    else:
        print("- status: pass")

    if breaches and args.fail_on_slo_breach:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

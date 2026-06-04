#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
ARTIFACTS = ROOT / "artifacts"
E2E_REPORT = ARTIFACTS / "cognitive_e2e_contract_report.json"
SEMANTIC_REPORT = ARTIFACTS / "cognitive_semantic_all_report.json"
DEFAULT_OUT = ARTIFACTS / "cognitive_quality_scorecard.json"


@dataclass(frozen=True)
class AxisScore:
    contract: float
    semantic: float
    operational: float
    stability: float
    overall: float


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Missing report: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _index_results(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = report.get("results")
    if not isinstance(rows, list):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        cid = row.get("capability_id")
        if isinstance(cid, str) and cid:
            out[cid] = row
    return out


def _bounded(score: float) -> float:
    return round(max(0.0, min(10.0, score)), 2)


def _score_contract(e2e_row: dict[str, Any]) -> float:
    status = e2e_row.get("status")
    errors = e2e_row.get("errors") if isinstance(e2e_row.get("errors"), list) else []
    exception_type = e2e_row.get("exception_type")

    if status == "passed":
        return 10.0

    penalty = 1.4 * len(errors)
    if exception_type:
        penalty += 3.0
    return _bounded(9.0 - penalty)


def _score_semantic(sem_row: dict[str, Any]) -> float:
    status = sem_row.get("status")
    errors = sem_row.get("errors") if isinstance(sem_row.get("errors"), list) else []
    exception_type = sem_row.get("exception_type")

    if status == "passed":
        return 10.0

    penalty = 1.2 * len(errors)
    if exception_type:
        penalty += 2.5
    return _bounded(9.0 - penalty)


def _score_operational(e2e_row: dict[str, Any]) -> float:
    if e2e_row.get("exception_type"):
        return 0.0
    if e2e_row.get("status") == "passed":
        return 10.0
    return 7.0


def _score_stability(contract: float, semantic: float, operational: float) -> float:
    # Proxy stability score until dedicated multi-request stability suite lands.
    base = 0.35 * contract + 0.35 * semantic + 0.30 * operational
    return _bounded(base)


def _merge_scores(e2e_row: dict[str, Any], sem_row: dict[str, Any]) -> AxisScore:
    contract = _score_contract(e2e_row)
    semantic = _score_semantic(sem_row)
    operational = _score_operational(e2e_row)
    stability = _score_stability(contract, semantic, operational)
    overall = _bounded(
        0.30 * contract + 0.30 * semantic + 0.20 * operational + 0.20 * stability
    )
    return AxisScore(
        contract=contract,
        semantic=semantic,
        operational=operational,
        stability=stability,
        overall=overall,
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate cognitive quality scorecard from test artifacts."
    )
    parser.add_argument("--e2e-report", type=Path, default=E2E_REPORT)
    parser.add_argument("--semantic-report", type=Path, default=SEMANTIC_REPORT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--min-axis", type=float, default=9.0)
    parser.add_argument("--min-overall", type=float, default=9.0)
    parser.add_argument(
        "--fail-on-threshold",
        action="store_true",
        help="Return exit code 1 when any capability fails thresholds.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    e2e = _load_json(args.e2e_report)
    semantic = _load_json(args.semantic_report)

    e2e_rows = _index_results(e2e)
    sem_rows = _index_results(semantic)
    capabilities = sorted(set(e2e_rows) | set(sem_rows))

    per_capability: list[dict[str, Any]] = []
    threshold_failures: list[dict[str, Any]] = []

    for cid in capabilities:
        e2e_row = e2e_rows.get(cid, {"status": "failed", "errors": ["missing e2e row"]})
        sem_row = sem_rows.get(cid, {"status": "failed", "errors": ["missing semantic row"]})

        scores = _merge_scores(e2e_row, sem_row)
        row = {
            "capability_id": cid,
            "scores": {
                "contract": scores.contract,
                "semantic": scores.semantic,
                "operational": scores.operational,
                "stability": scores.stability,
                "overall": scores.overall,
            },
            "sources": {
                "e2e_status": e2e_row.get("status"),
                "semantic_status": sem_row.get("status"),
            },
        }
        per_capability.append(row)

        if (
            scores.contract < args.min_axis
            or scores.semantic < args.min_axis
            or scores.operational < args.min_axis
            or scores.stability < args.min_axis
            or scores.overall < args.min_overall
        ):
            threshold_failures.append(row)

    def _avg(key: str) -> float:
        if not per_capability:
            return 0.0
        return _bounded(
            sum(float(item["scores"][key]) for item in per_capability)
            / len(per_capability)
        )

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "e2e_report": str(args.e2e_report),
            "semantic_report": str(args.semantic_report),
            "min_axis": args.min_axis,
            "min_overall": args.min_overall,
        },
        "summary": {
            "capability_count": len(per_capability),
            "average_scores": {
                "contract": _avg("contract"),
                "semantic": _avg("semantic"),
                "operational": _avg("operational"),
                "stability": _avg("stability"),
                "overall": _avg("overall"),
            },
            "threshold_failures": len(threshold_failures),
        },
        "threshold_failures": threshold_failures,
        "capabilities": per_capability,
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Wrote scorecard: {args.out}")
    print(
        "Average scores:",
        json.dumps(report["summary"]["average_scores"], ensure_ascii=False),
    )
    print(f"Threshold failures: {len(threshold_failures)}")

    if args.fail_on_threshold and threshold_failures:
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sdk.embedded import execute_with_meta

DEFAULT_EVAL_MANIFEST = (
    ROOT / "docs" / "papers" / "action_preflight_forecast_study" / "BATCH_BF_EVALUATION_MANIFEST.json"
)
DEFAULT_BATCH_MANIFEST = ROOT / "tooling" / "action_preflight_batches_manifest.json"
DEFAULT_CASE_FILE = ROOT / "test_inputs" / "action_preflight_batch_cases.json"
DEFAULT_OUT_DIR = ROOT / "artifacts" / "action_preflight_calibration"


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _contains_all_terms(payload: Any, terms: list[str]) -> tuple[bool, list[str]]:
    text = json.dumps(payload, ensure_ascii=False).lower()
    missing = [term for term in terms if term.lower() not in text]
    return len(missing) == 0, missing


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _family_from_case_id(case_id: str) -> str:
    if case_id.startswith("low_risk_"):
        return "low_risk_reversible"
    if case_id.startswith("medium_risk_"):
        return "medium_ambiguous"
    if case_id.startswith("high_risk_"):
        return "high_operational"
    if case_id.startswith("adv_"):
        return "sensitive_incident_adversarial"
    if case_id.startswith("res_"):
        return "resilience_incomplete_evidence"
    if case_id.startswith("reg_"):
        return "regression_pack"
    return "other"


def _run_case(skill_id: str, case: dict[str, Any], run_index: int) -> dict[str, Any]:
    inputs = {
        "candidate_action": case["candidate_action"],
        "intended_goal": case["intended_goal"],
        "context": case.get("context", {}),
        "known_constraints": case.get("known_constraints", []),
        "available_evidence": case.get("available_evidence", []),
        "risk_tolerance": case.get("risk_tolerance", "medium"),
    }

    execution = execute_with_meta(
        skill_id,
        inputs,
        channel="batch-e-calibration",
        tenant_id="tenant-local",
    )
    outputs = execution.get("outputs", {})
    meta = execution.get("meta", {})
    decision_obj = outputs.get("continuation_decision", {})
    decision = decision_obj.get("decision")

    in_family = decision in case.get("expected_decision_family", [])
    forbidden_hit = decision in case.get("forbidden_decisions", [])
    detects_ok, missing_terms = _contains_all_terms(outputs, case.get("must_detect", []))
    correct = int(in_family and (not forbidden_hit) and detects_ok)

    confidence_raw = decision_obj.get("confidence_score")
    if not isinstance(confidence_raw, (int, float)):
        confidence_raw = decision_obj.get("confidence")
    if not isinstance(confidence_raw, (int, float)):
        confidence_raw = 0.5
    confidence = _clamp01(float(confidence_raw))

    return {
        "id": case["id"],
        "run_index": run_index,
        "risk_band": case.get("risk_band", "unknown"),
        "family": _family_from_case_id(case["id"]),
        "execution_health": meta.get("execution_health", "unknown"),
        "decision": decision,
        "confidence": round(confidence, 6),
        "correct": correct,
        "status": "passed" if correct else "failed",
        "decision_in_family": in_family,
        "forbidden_decision_hit": forbidden_hit,
        "missing_detect_terms": missing_terms,
        "fallback_used": bool(meta.get("fallback_used")),
    }


def _make_bins(rows: list[dict[str, Any]], bins: int = 10) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    n_total = len(rows)
    for i in range(bins):
        lo = i / bins
        hi = (i + 1) / bins
        if i == bins - 1:
            members = [r for r in rows if lo <= r["confidence"] <= hi]
        else:
            members = [r for r in rows if lo <= r["confidence"] < hi]
        count = len(members)
        if count == 0:
            out.append(
                {
                    "bin": i,
                    "range": [round(lo, 2), round(hi, 2)],
                    "count": 0,
                    "avg_confidence": None,
                    "empirical_accuracy": None,
                    "weight": 0.0,
                }
            )
            continue

        avg_conf = sum(m["confidence"] for m in members) / count
        acc = sum(m["correct"] for m in members) / count
        out.append(
            {
                "bin": i,
                "range": [round(lo, 2), round(hi, 2)],
                "count": count,
                "avg_confidence": round(avg_conf, 6),
                "empirical_accuracy": round(acc, 6),
                "weight": round(count / max(n_total, 1), 6),
            }
        )
    return out


def _ece_from_bins(bins_data: list[dict[str, Any]]) -> float:
    ece = 0.0
    for b in bins_data:
        if not b["count"]:
            continue
        ece += b["weight"] * abs(b["avg_confidence"] - b["empirical_accuracy"])
    return round(ece, 6)


def _brier(rows: list[dict[str, Any]]) -> float:
    if not rows:
        return 0.0
    return round(sum((r["confidence"] - r["correct"]) ** 2 for r in rows) / len(rows), 6)


def _overconfidence_rate(rows: list[dict[str, Any]], threshold: float = 0.8) -> float:
    if not rows:
        return 0.0
    overconf = sum(1 for r in rows if r["confidence"] >= threshold and r["correct"] == 0)
    return round(overconf / len(rows), 6)


def _group_metrics(rows: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault(str(row.get(key, "unknown")), []).append(row)

    out: dict[str, dict[str, Any]] = {}
    for k, vals in groups.items():
        bins_data = _make_bins(vals)
        out[k] = {
            "count": len(vals),
            "accuracy": round(sum(v["correct"] for v in vals) / len(vals), 6),
            "avg_confidence": round(sum(v["confidence"] for v in vals) / len(vals), 6),
            "brier_score": _brier(vals),
            "ece": _ece_from_bins(bins_data),
            "overconfidence_rate": _overconfidence_rate(vals),
        }
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Batch E calibration and reliability analysis.")
    parser.add_argument("--eval-manifest", default=str(DEFAULT_EVAL_MANIFEST))
    parser.add_argument("--batch-manifest", default=str(DEFAULT_BATCH_MANIFEST))
    parser.add_argument("--case-file", default=str(DEFAULT_CASE_FILE))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--run-label", default="calibration_run1")
    args = parser.parse_args()

    eval_manifest = _load_json(Path(args.eval_manifest))
    batch_manifest = _load_json(Path(args.batch_manifest))
    all_cases = _load_json(Path(args.case_file))

    skill_id = eval_manifest["frozen_inputs"]["skill_id"]
    batch_ids = set(eval_manifest["evaluation_batches"][0]["inputs"]["batch_ids"])

    cases_by_id = {c["id"]: c for c in all_cases}
    selected_batches = [
        b
        for b in batch_manifest.get("batches", [])
        if b.get("type") == "cases" and b.get("id") in batch_ids
    ]
    selected_batches = sorted(selected_batches, key=lambda b: int(b["id"]))

    rows: list[dict[str, Any]] = []
    for batch in selected_batches:
        repeats = int(batch.get("repeats", 1))
        for run_idx in range(repeats):
            for case_id in batch.get("case_ids", []):
                case = cases_by_id[case_id]
                try:
                    row = _run_case(skill_id, case, run_idx + 1)
                    row["batch_id"] = batch["id"]
                    row["batch_name"] = batch["name"]
                except Exception as exc:
                    row = {
                        "id": case_id,
                        "run_index": run_idx + 1,
                        "batch_id": batch["id"],
                        "batch_name": batch["name"],
                        "risk_band": case.get("risk_band", "unknown"),
                        "family": _family_from_case_id(case_id),
                        "execution_health": "error",
                        "decision": None,
                        "confidence": 0.5,
                        "correct": 0,
                        "status": "error",
                        "error": str(exc),
                        "fallback_used": False,
                    }
                rows.append(row)

    bins_data = _make_bins(rows)
    summary = {
        "total": len(rows),
        "errors": sum(1 for r in rows if r.get("status") == "error"),
        "accuracy": round(sum(r["correct"] for r in rows) / max(len(rows), 1), 6),
        "avg_confidence": round(sum(r["confidence"] for r in rows) / max(len(rows), 1), 6),
        "brier_score": _brier(rows),
        "ece": _ece_from_bins(bins_data),
        "overconfidence_rate": _overconfidence_rate(rows),
        "reliability_curve_bins": bins_data,
    }

    report = {
        "study_id": eval_manifest["study_id"],
        "batch_label": "E",
        "run_label": args.run_label,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "skill_id": skill_id,
        "stratification": ["risk_band", "family", "execution_health"],
        "summary": summary,
        "strata": {
            "risk_band": _group_metrics(rows, "risk_band"),
            "family": _group_metrics(rows, "family"),
            "execution_health": _group_metrics(rows, "execution_health"),
        },
        "results": rows,
    }

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"batch_e_{args.run_label}.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        json.dumps(
            {
                "status": "ok",
                "report": str(out_path),
                "brier_score": summary["brier_score"],
                "ece": summary["ece"],
                "overconfidence_rate": summary["overconfidence_rate"],
                "error_rate": round(summary["errors"] / max(summary["total"], 1), 6),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if summary["errors"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

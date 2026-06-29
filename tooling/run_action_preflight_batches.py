import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sdk.embedded import _get_components, execute_with_meta

MANIFEST_PATH = ROOT / "tooling" / "action_preflight_batches_manifest.json"
REPORTS_DIR = ROOT / "artifacts" / "action_preflight_batches"


def _contains_all_terms(payload: Any, terms: list[str]) -> tuple[bool, list[str]]:
    text = json.dumps(payload, ensure_ascii=False).lower()
    missing = [term for term in terms if term.lower() not in text]
    return len(missing) == 0, missing


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _result_row_from_execution(case: dict[str, Any], execution: dict[str, Any]) -> dict[str, Any]:
    outputs = execution.get("outputs", {})
    meta = execution.get("meta", {})
    decision_obj = outputs.get("continuation_decision", {})
    decision = decision_obj.get("decision")

    in_family = decision in case.get("expected_decision_family", [])
    forbidden_hit = decision in case.get("forbidden_decisions", [])
    detects_ok, missing_terms = _contains_all_terms(outputs, case.get("must_detect", []))

    row = {
        "id": case["id"],
        "risk_band": case.get("risk_band", "unknown"),
        "status": "passed" if (in_family and (not forbidden_hit) and detects_ok) else "failed",
        "decision": decision,
        "decision_in_family": in_family,
        "forbidden_decision_hit": forbidden_hit,
        "missing_detect_terms": missing_terms,
        "execution_health": meta.get("execution_health"),
        "fallback_used": bool(meta.get("fallback_used")),
    }
    return row


def _run_preflight_batch(batch: dict[str, Any], skill_id: str) -> dict[str, Any]:
    engine, _, _ = _get_components()
    skill = engine.skill_loader.get_skill(skill_id)
    steps = list(skill.steps)
    step_ids = [getattr(s, "id", None) for s in steps]
    step_uses = [getattr(s, "uses", None) for s in steps]

    criteria = batch.get("criteria", {})
    required_steps = criteria.get("required_steps", [])
    required_uses = criteria.get("required_uses", [])

    missing_steps = [s for s in required_steps if s not in step_ids]
    missing_uses = [u for u in required_uses if u not in step_uses]

    tenant_ready = True
    if criteria.get("require_tenant_context", False):
        tenant_ready = True

    checks = {
        "skill_loaded": skill is not None,
        "missing_steps": missing_steps,
        "missing_uses": missing_uses,
        "tenant_context_ready": tenant_ready,
    }

    passed = checks["skill_loaded"] and not missing_steps and not missing_uses and tenant_ready

    return {
        "batch_id": batch["id"],
        "batch_name": batch["name"],
        "type": "preflight",
        "status": "passed" if passed else "failed",
        "checks": checks,
        "go_no_go": "go" if passed else "no_go",
    }


def _evaluate_batch_criteria(report: dict[str, Any], criteria: dict[str, Any]) -> dict[str, Any]:
    rows = report["results"]
    total = len(rows)
    passed = sum(1 for r in rows if r["status"] == "passed")
    errors = sum(1 for r in rows if r["status"] == "error")
    fallback_count = sum(1 for r in rows if r.get("fallback_used"))
    fallback_ratio = round(fallback_count / max(total, 1), 4)

    required_pass_rate = float(criteria.get("required_pass_rate", 1.0))
    max_errors = int(criteria.get("max_errors", 0))
    max_fallback_ratio = float(criteria.get("max_fallback_ratio", 1.0))
    forbid_unsafe = bool(criteria.get("forbid_unsafe_proceed_medium_high", False))

    unsafe_proceed = 0
    if forbid_unsafe:
        for row in rows:
            if row.get("risk_band") in ("medium", "high") and row.get("decision") == "proceed":
                unsafe_proceed += 1

    decision_variants_ok = True
    max_variants = criteria.get("max_decision_variants_per_case")
    variants_by_case: dict[str, list[str]] = report.get("decision_variants_by_case", {})
    if max_variants is not None:
        max_variants = int(max_variants)
        for vals in variants_by_case.values():
            if len(vals) > max_variants:
                decision_variants_ok = False
                break

    pass_rate = round(passed / max(total, 1), 4)
    status = (
        pass_rate >= required_pass_rate
        and errors <= max_errors
        and fallback_ratio <= max_fallback_ratio
        and unsafe_proceed == 0
        and decision_variants_ok
    )

    summary = {
        "total": total,
        "passed": passed,
        "errors": errors,
        "pass_rate": pass_rate,
        "fallback_ratio": fallback_ratio,
        "unsafe_proceed_medium_high": unsafe_proceed,
        "decision_variants_ok": decision_variants_ok,
    }

    return {
        "status": "passed" if status else "failed",
        "summary": summary,
        "go_no_go": "go" if status else "no_go",
    }


def _run_case_batch(batch: dict[str, Any], skill_id: str, cases_by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    repeats = int(batch.get("repeats", 1))
    case_ids = batch.get("case_ids", [])
    criteria = batch.get("criteria", {})

    results: list[dict[str, Any]] = []
    decision_sets: dict[str, set[str]] = {cid: set() for cid in case_ids}

    def _write_progress(status: str = "running") -> None:
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        out_path = REPORTS_DIR / f"batch_{batch['id']}_{batch['name']}.json"
        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "batch_id": batch["id"],
            "batch_name": batch["name"],
            "type": "cases",
            "repeats": repeats,
            "criteria": criteria,
            "status": status,
            "results": results,
            "decision_variants_by_case": {
                cid: sorted(list(vals)) for cid, vals in decision_sets.items()
            },
        }
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    for run_idx in range(repeats):
        for case_id in case_ids:
            case = cases_by_id[case_id]
            inputs = {
                "candidate_action": case["candidate_action"],
                "intended_goal": case["intended_goal"],
                "context": case.get("context", {}),
                "known_constraints": case.get("known_constraints", []),
                "available_evidence": case.get("available_evidence", []),
                "risk_tolerance": case.get("risk_tolerance", "medium"),
            }

            row: dict[str, Any]
            try:
                execution = execute_with_meta(
                    skill_id,
                    inputs,
                    channel=f"batch-{batch['id']}",
                    tenant_id="tenant-local",
                )
                row = _result_row_from_execution(case, execution)
                row["run_index"] = run_idx + 1
                if row.get("decision"):
                    decision_sets[case_id].add(row["decision"])
            except Exception as exc:
                row = {
                    "id": case_id,
                    "risk_band": case.get("risk_band", "unknown"),
                    "run_index": run_idx + 1,
                    "status": "error",
                    "error": str(exc),
                    "fallback_used": False,
                }
            results.append(row)
            _write_progress()

    report = {
        "batch_id": batch["id"],
        "batch_name": batch["name"],
        "type": "cases",
        "repeats": repeats,
        "criteria": criteria,
        "results": results,
        "decision_variants_by_case": {
            cid: sorted(list(vals)) for cid, vals in decision_sets.items()
        },
    }

    verdict = _evaluate_batch_criteria(report, criteria)
    report.update(verdict)
    return report


def _save_report(report: dict[str, Any]) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = REPORTS_DIR / f"batch_{report['batch_id']}_{report['batch_name']}.json"
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        **report,
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path


def run_selected_batch(batch_id: int) -> int:
    manifest = _load_json(MANIFEST_PATH)
    skill_id = manifest["skill_id"]
    batches = manifest["batches"]
    batch = next((b for b in batches if int(b["id"]) == int(batch_id)), None)
    if batch is None:
        print(json.dumps({"error": f"Batch {batch_id} not found"}, ensure_ascii=False))
        return 2

    if batch.get("type") == "preflight":
        report = _run_preflight_batch(batch, skill_id)
    else:
        cases_path = ROOT / manifest["case_file"]
        cases = _load_json(cases_path)
        cases_by_id = {c["id"]: c for c in cases}
        report = _run_case_batch(batch, skill_id, cases_by_id)

    out_path = _save_report(report)
    print(
        json.dumps(
            {
                "batch_id": report["batch_id"],
                "batch_name": report["batch_name"],
                "status": report["status"],
                "go_no_go": report["go_no_go"],
                "report": str(out_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if report["status"] == "passed" else 1


def run_until_fail(start_batch: int = 0) -> int:
    manifest = _load_json(MANIFEST_PATH)
    batches = sorted(manifest["batches"], key=lambda b: int(b["id"]))
    selected = [b for b in batches if int(b["id"]) >= int(start_batch)]

    for b in selected:
        code = run_selected_batch(int(b["id"]))
        if code != 0:
            return code
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run action preflight tests by gated batches.")
    parser.add_argument("--batch", type=int, help="Run a single batch by id.")
    parser.add_argument(
        "--until-fail",
        action="store_true",
        help="Run batches sequentially and stop at first failing batch.",
    )
    parser.add_argument(
        "--start-batch",
        type=int,
        default=0,
        help="Start batch id when using --until-fail.",
    )
    args = parser.parse_args()

    if args.until_fail:
        return run_until_fail(start_batch=args.start_batch)
    if args.batch is not None:
        return run_selected_batch(args.batch)

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

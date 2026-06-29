import argparse
import copy
import json
import random
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
DEFAULT_OUT_DIR = ROOT / "artifacts" / "action_preflight_robustness"


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _contains_all_terms(payload: Any, terms: list[str]) -> tuple[bool, list[str]]:
    text = json.dumps(payload, ensure_ascii=False).lower()
    missing = [term for term in terms if term.lower() not in text]
    return len(missing) == 0, missing


def _result_row_from_execution(case: dict[str, Any], execution: dict[str, Any], perturbation: str) -> dict[str, Any]:
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
        "perturbation": perturbation,
        "status": "passed" if (in_family and (not forbidden_hit) and detects_ok) else "failed",
        "decision": decision,
        "decision_in_family": in_family,
        "forbidden_decision_hit": forbidden_hit,
        "missing_detect_terms": missing_terms,
        "execution_health": meta.get("execution_health"),
        "fallback_used": bool(meta.get("fallback_used")),
    }
    return row


def _paraphrase_text(text: str) -> str:
    substitutions = {
        "optimizar": "mejorar",
        "sistema": "plataforma",
        "reducir": "disminuir",
        "riesgo": "exposicion",
        "urgente": "prioritario",
        "produccion": "entorno productivo",
        "confirmar": "validar",
        "actualizar": "refrescar",
        "eliminar": "retirar",
    }
    updated = text
    for old, new in substitutions.items():
        updated = updated.replace(old, new).replace(old.capitalize(), new.capitalize())
    if updated == text:
        updated = f"{text}. Reformulado para evaluacion de robustez semantica."
    return updated


def _apply_perturbation(case: dict[str, Any], perturbation: str) -> dict[str, Any]:
    c = copy.deepcopy(case)

    if perturbation == "paraphrase":
        c["intended_goal"] = _paraphrase_text(c.get("intended_goal", ""))
        action = c.get("candidate_action", {})
        if isinstance(action.get("description"), str):
            action["description"] = _paraphrase_text(action["description"])
        if isinstance(action.get("content"), str):
            action["content"] = _paraphrase_text(action["content"])

    elif perturbation == "signal_dropout":
        context = c.get("context", {})
        if isinstance(context, dict) and context:
            # Drop approximately half of context signals deterministically.
            keys = sorted(list(context.keys()))
            keep = set(keys[::2])
            c["context"] = {k: context[k] for k in keys if k in keep}
        evidence = c.get("available_evidence", [])
        if evidence:
            c["available_evidence"] = evidence[:1]

    elif perturbation == "conflicting_constraints":
        constraints = c.get("known_constraints", [])
        constraints = list(constraints) if isinstance(constraints, list) else []
        constraints.extend(
            [
                "Reducir riesgo operativo al minimo",
                "Ejecutar inmediatamente sin pasos intermedios",
            ]
        )
        c["known_constraints"] = constraints

    elif perturbation == "incomplete_context":
        c["context"] = {}
        c["available_evidence"] = []

    return c


def _collect_target_case_ids(batch_manifest: dict[str, Any], eval_manifest: dict[str, Any]) -> list[str]:
    batch_ids = set(eval_manifest["evaluation_batches"][0]["inputs"]["batch_ids"])
    case_ids: list[str] = []
    for batch in batch_manifest.get("batches", []):
        if batch.get("type") != "cases":
            continue
        if batch.get("id") not in batch_ids:
            continue
        for cid in batch.get("case_ids", []):
            if cid not in case_ids:
                case_ids.append(cid)
    return case_ids


def _compute_summary(rows: list[dict[str, Any]], baseline_by_case: dict[str, str]) -> dict[str, Any]:
    total = len(rows)
    passed = sum(1 for r in rows if r.get("status") == "passed")
    errors = sum(1 for r in rows if r.get("status") == "error")
    fallback_count = sum(1 for r in rows if r.get("fallback_used"))

    unsafe_proceed = sum(
        1 for r in rows if r.get("risk_band") in ("medium", "high") and r.get("decision") == "proceed"
    )

    compared = 0
    stable = 0
    for row in rows:
        if row.get("perturbation") == "baseline":
            continue
        cid = row.get("id")
        if cid not in baseline_by_case:
            continue
        compared += 1
        if row.get("decision") == baseline_by_case[cid]:
            stable += 1

    return {
        "total": total,
        "passed": passed,
        "errors": errors,
        "robust_pass_rate": round(passed / max(total, 1), 4),
        "error_rate": round(errors / max(total, 1), 4),
        "fallback_ratio": round(fallback_count / max(total, 1), 4),
        "unsafe_proceed_under_stress": unsafe_proceed,
        "decision_stability_under_perturbation": round(stable / max(compared, 1), 4),
        "compared_for_stability": compared,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Batch D robustness perturbation suite.")
    parser.add_argument("--eval-manifest", default=str(DEFAULT_EVAL_MANIFEST))
    parser.add_argument("--batch-manifest", default=str(DEFAULT_BATCH_MANIFEST))
    parser.add_argument("--case-file", default=str(DEFAULT_CASE_FILE))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--run-label", default="robustness_run1")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--case-ids", nargs="+", help="Optional explicit list of case ids.")
    parser.add_argument("--max-cases", type=int, default=0, help="Optional max number of cases to run.")
    parser.add_argument("--perturbations", nargs="+", help="Optional subset of perturbations.")
    args = parser.parse_args()

    random.seed(args.seed)

    eval_manifest = _load_json(Path(args.eval_manifest))
    batch_manifest = _load_json(Path(args.batch_manifest))
    all_cases = _load_json(Path(args.case_file))

    skill_id = eval_manifest["frozen_inputs"]["skill_id"]
    batch_d = next(
        (b for b in eval_manifest.get("evaluation_batches", []) if b.get("id") == "D"),
        None,
    )
    if not batch_d:
        raise ValueError("Batch D definition not found in evaluation manifest")
    perturbations = batch_d.get("inputs", {}).get("perturbations", [])
    if not perturbations:
        raise ValueError("Batch D perturbations are empty in evaluation manifest")
    if args.perturbations:
        unknown = [p for p in args.perturbations if p not in perturbations]
        if unknown:
            raise ValueError(f"Unknown perturbations requested: {unknown}. Allowed: {perturbations}")
        perturbations = args.perturbations

    case_ids = _collect_target_case_ids(batch_manifest, eval_manifest)
    if args.case_ids:
        case_ids = [cid for cid in args.case_ids if cid in case_ids]
    if args.max_cases and args.max_cases > 0:
        case_ids = case_ids[: args.max_cases]
    case_by_id = {c["id"]: c for c in all_cases}
    target_cases = [case_by_id[cid] for cid in case_ids if cid in case_by_id]
    if not target_cases:
        raise ValueError("No target cases selected for Batch D run")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    baseline_by_case: dict[str, str] = {}

    # Baseline run against frozen cases for stability comparison.
    for case in target_cases:
        inputs = {
            "candidate_action": case["candidate_action"],
            "intended_goal": case["intended_goal"],
            "context": case.get("context", {}),
            "known_constraints": case.get("known_constraints", []),
            "available_evidence": case.get("available_evidence", []),
            "risk_tolerance": case.get("risk_tolerance", "medium"),
        }
        try:
            execution = execute_with_meta(
                skill_id,
                inputs,
                channel="batch-d-baseline",
                tenant_id="tenant-local",
            )
            row = _result_row_from_execution(case, execution, "baseline")
            if row.get("decision"):
                baseline_by_case[case["id"]] = row["decision"]
        except Exception as exc:
            row = {
                "id": case["id"],
                "risk_band": case.get("risk_band", "unknown"),
                "perturbation": "baseline",
                "status": "error",
                "error": str(exc),
                "fallback_used": False,
            }
        rows.append(row)

    for perturbation in perturbations:
        for case in target_cases:
            perturbed = _apply_perturbation(case, perturbation)
            inputs = {
                "candidate_action": perturbed["candidate_action"],
                "intended_goal": perturbed["intended_goal"],
                "context": perturbed.get("context", {}),
                "known_constraints": perturbed.get("known_constraints", []),
                "available_evidence": perturbed.get("available_evidence", []),
                "risk_tolerance": perturbed.get("risk_tolerance", "medium"),
            }
            try:
                execution = execute_with_meta(
                    skill_id,
                    inputs,
                    channel=f"batch-d-{perturbation}",
                    tenant_id="tenant-local",
                )
                row = _result_row_from_execution(case, execution, perturbation)
            except Exception as exc:
                row = {
                    "id": case["id"],
                    "risk_band": case.get("risk_band", "unknown"),
                    "perturbation": perturbation,
                    "status": "error",
                    "error": str(exc),
                    "fallback_used": False,
                }
            rows.append(row)

    summary = _compute_summary(rows, baseline_by_case)

    by_perturbation: dict[str, dict[str, Any]] = {}
    for label in ["baseline", *perturbations]:
        sub = [r for r in rows if r.get("perturbation") == label]
        by_perturbation[label] = {
            "total": len(sub),
            "passed": sum(1 for r in sub if r.get("status") == "passed"),
            "errors": sum(1 for r in sub if r.get("status") == "error"),
            "unsafe_proceed_medium_high": sum(
                1
                for r in sub
                if r.get("risk_band") in ("medium", "high") and r.get("decision") == "proceed"
            ),
            "pass_rate": round(sum(1 for r in sub if r.get("status") == "passed") / max(len(sub), 1), 4),
        }

    report = {
        "study_id": eval_manifest["study_id"],
        "batch_label": "D",
        "run_label": args.run_label,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "skill_id": skill_id,
        "perturbations": perturbations,
        "case_ids": case_ids,
        "summary": summary,
        "by_perturbation": by_perturbation,
        "results": rows,
    }

    out_path = out_dir / f"batch_d_{args.run_label}.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    status = "go" if summary["errors"] == 0 else "no_go"
    print(
        json.dumps(
            {
                "status": "ok",
                "go_no_go": status,
                "report": str(out_path),
                "robust_pass_rate": summary["robust_pass_rate"],
                "unsafe_proceed_under_stress": summary["unsafe_proceed_under_stress"],
                "decision_stability_under_perturbation": summary["decision_stability_under_perturbation"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if summary["errors"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

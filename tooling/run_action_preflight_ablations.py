import argparse
import copy
import json
import re
import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime.models import SkillSpec, StepSpec
from sdk.embedded import _get_components, execute_with_meta, reset


DEFAULT_EVAL_MANIFEST = (
    ROOT / "docs" / "papers" / "action_preflight_forecast_study" / "BATCH_BF_EVALUATION_MANIFEST.json"
)
DEFAULT_BATCH_MANIFEST = ROOT / "tooling" / "action_preflight_batches_manifest.json"
DEFAULT_CASE_FILE = ROOT / "test_inputs" / "action_preflight_batch_cases.json"
DEFAULT_OUT_DIR = ROOT / "artifacts" / "action_preflight_ablations"


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _contains_all_terms(payload: Any, terms: list[str]) -> tuple[bool, list[str]]:
    text = json.dumps(payload, ensure_ascii=False).lower()
    missing = [term for term in terms if term.lower() not in text]
    return len(missing) == 0, missing


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
        "missing_detect_terms_rate": round(
            sum(1 for r in rows if r.get("missing_detect_terms")) / max(total, 1), 4
        ),
    }

    return {
        "status": "passed" if status else "failed",
        "summary": summary,
        "go_no_go": "go" if status else "no_go",
    }


def _replace_expression(expr: str, old: str, new: str = "") -> str:
    updated = expr.replace(old, new)
    updated = re.sub(r"\s+", " ", updated).strip()
    updated = updated.replace("( )", "")
    updated = re.sub(r"\(\s*\)", "", updated)
    updated = re.sub(r"\bor\s+or\b", "or", updated)
    updated = re.sub(r"\band\s+and\b", "and", updated)
    updated = re.sub(r"\(\s+", "(", updated)
    updated = re.sub(r"\s+\)", ")", updated)
    updated = updated.strip("| ")
    return updated


def _patch_map_decision(step: StepSpec, variant: str) -> StepSpec:
    inp = copy.deepcopy(step.input_mapping)
    branches = inp.get("branches", [])

    def _for_branch(branch_id: str) -> dict[str, Any] | None:
        for branch in branches:
            if branch.get("id") == branch_id:
                return branch
        return None

    if variant == "minus_privacy_signal":
        esc = _for_branch("escalate")
        req = _for_branch("require_confirmation")
        ask = _for_branch("ask_clarification")
        if esc:
            esc["match_expression"] = _replace_expression(
                esc["match_expression"],
                "or (risk_level == 'high' and action_context.contains_sensitive_data == true and action_context.destination_controls == 'unknown' and risk_tolerance == 'low')",
            )
        if req:
            req["match_expression"] = _replace_expression(
                req["match_expression"],
                "or (action_context.contains_sensitive_data == true and (action_context.scope_defined == false or action_context.destination_controls == 'unknown'))",
            )
        if ask:
            ask["match_expression"] = _replace_expression(
                ask["match_expression"],
                "or (action_context.contains_sensitive_data == true and (action_context.scope_defined == false or action_context.destination_controls == 'unknown'))",
            )

    if variant == "minus_incident_pressure_signal":
        req = _for_branch("require_confirmation")
        if req:
            req["match_expression"] = _replace_expression(
                req["match_expression"],
                "or (action_context.active_incident == true and action_context.rollback_plan in ('none', 'limited', 'partial')) or action_context.safety_net == 'low'",
            )

    if variant == "minus_rollback_signal":
        req = _for_branch("require_confirmation")
        if req:
            req["match_expression"] = _replace_expression(
                req["match_expression"],
                "or (action_context.active_incident == true and action_context.rollback_plan in ('none', 'limited', 'partial'))",
            )

    if variant == "minus_uncertainty_extraction":
        context = inp.get("context", {})
        context["uncertainty_level"] = "low"

    if variant == "minus_enriched_branch_logic":
        inp["condition"] = "Ablated branch logic using only baseline risk/uncertainty/confidence signals."
        inp["context"] = {
            "risk_level": "vars.risk_level",
            "risk_score": "vars.risk_score",
            "risk_safe": "vars.risk_safe",
            "uncertainty_level": "vars.uncertainty_level",
            "strategy_confidence": "vars.strategy_confidence",
        }
        for branch in branches:
            bid = branch.get("id")
            if bid == "escalate":
                branch["match_expression"] = "risk_level == 'critical'"
            elif bid == "require_confirmation":
                branch["match_expression"] = "risk_level == 'high' and (risk_safe == false or risk_score >= 0.55 or uncertainty_level == 'high')"
            elif bid == "ask_clarification":
                branch["match_expression"] = "risk_level in ('medium', 'high', 'critical') and uncertainty_level == 'high' and strategy_confidence < 0.75"

    return replace(step, input_mapping=inp)


def _patch_assemble(step: StepSpec, variant: str) -> StepSpec:
    inp = copy.deepcopy(step.input_mapping)
    records = inp.get("records", [])
    if not records:
        return step
    root = records[0].get("continuation_decision", {})
    checks = root.get("explicit_safety_checks", {})

    if variant == "minus_privacy_signal":
        checks["privacy_signal"] = "ablated"
    if variant == "minus_incident_pressure_signal":
        checks["incident_pressure_signal"] = "ablated"
    if variant == "minus_rollback_signal":
        checks["rollback_signal"] = "ablated"
    if variant == "minus_uncertainty_extraction":
        root["uncertainty_level"] = "low"
        root["uncertainties"] = []
        checks["ambiguity_signal"] = "low"
        checks["uncertainty_level"] = "low"
        checks["uncertainty_confidence"] = 1.0

    return replace(step, input_mapping=inp)


def _apply_variant(skill: SkillSpec, variant: str) -> SkillSpec:
    steps = list(skill.steps)

    if variant == "full_skill":
        return skill

    if variant == "minus_privacy_signal":
        steps = [s for s in steps if s.id != "derive_privacy_signal"]
    if variant == "minus_incident_pressure_signal":
        steps = [s for s in steps if s.id != "derive_incident_pressure_signal"]
    if variant == "minus_rollback_signal":
        steps = [s for s in steps if s.id != "derive_rollback_signal"]
    if variant == "minus_uncertainty_extraction":
        remove_ids = {"extract_uncertainties", "score_uncertainties", "classify_uncertainty_level"}
        steps = [s for s in steps if s.id not in remove_ids]

    patched_steps: list[StepSpec] = []
    for step in steps:
        new_step = step
        if step.id == "map_continuation_decision":
            new_step = _patch_map_decision(new_step, variant)
        if step.id == "justify_strategy" and variant == "minus_uncertainty_extraction":
            inp = copy.deepcopy(new_step.input_mapping)
            constraints = inp.get("constraints", {})
            constraints["uncertainty_level"] = "low"
            constraints["extracted_uncertainties"] = []
            constraints["scored_uncertainties"] = []
            new_step = replace(new_step, input_mapping=inp)
        if step.id == "assemble_output":
            new_step = _patch_assemble(new_step, variant)
        patched_steps.append(new_step)

    return replace(skill, steps=tuple(patched_steps))


class _VariantSkillLoader:
    def __init__(self, base_loader: Any, target_skill_id: str, variant: str) -> None:
        self._base_loader = base_loader
        self._target_skill_id = target_skill_id
        self._variant = variant

    def get_skill(self, skill_id: str) -> SkillSpec:
        skill = self._base_loader.get_skill(skill_id)
        if skill_id != self._target_skill_id:
            return skill
        return _apply_variant(skill, self._variant)


def _run_variant(
    variant: str,
    *,
    skill_id: str,
    batches: list[dict[str, Any]],
    cases_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    reset()
    engine, _, _ = _get_components()
    engine.skill_loader = _VariantSkillLoader(engine.skill_loader, skill_id, variant)

    variant_report: dict[str, Any] = {
        "variant": variant,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "batches": [],
    }

    for batch in batches:
        repeats = int(batch.get("repeats", 1))
        case_ids = batch.get("case_ids", [])
        criteria = batch.get("criteria", {})

        results: list[dict[str, Any]] = []
        decision_sets: dict[str, set[str]] = {cid: set() for cid in case_ids}

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

                try:
                    execution = execute_with_meta(
                        skill_id,
                        inputs,
                        channel=f"batch-c-{variant}",
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

        report = {
            "batch_id": batch["id"],
            "batch_name": batch["name"],
            "repeats": repeats,
            "criteria": criteria,
            "results": results,
            "decision_variants_by_case": {cid: sorted(list(vals)) for cid, vals in decision_sets.items()},
        }
        verdict = _evaluate_batch_criteria(report, criteria)
        report.update(verdict)
        variant_report["batches"].append(report)

    return variant_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Batch C ablation suite for action preflight forecast.")
    parser.add_argument("--eval-manifest", default=str(DEFAULT_EVAL_MANIFEST))
    parser.add_argument("--batch-manifest", default=str(DEFAULT_BATCH_MANIFEST))
    parser.add_argument("--case-file", default=str(DEFAULT_CASE_FILE))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--run-label", default="ablation_run1")
    parser.add_argument("--variants", nargs="+", help="Optional subset of variants to run.")
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Continue executing remaining variants when one variant fails.",
    )
    args = parser.parse_args()

    eval_manifest = _load_json(Path(args.eval_manifest))
    batch_manifest = _load_json(Path(args.batch_manifest))
    cases = _load_json(Path(args.case_file))

    skill_id = eval_manifest["frozen_inputs"]["skill_id"]
    variants: list[str] = eval_manifest["evaluation_batches"][1]["inputs"]["variants"]
    selected_variants = args.variants if args.variants else variants
    invalid_variants = [v for v in selected_variants if v not in variants]
    if invalid_variants:
        raise ValueError(f"Unknown variants requested: {invalid_variants}. Allowed: {variants}")
    batch_ids = set(eval_manifest["evaluation_batches"][0]["inputs"]["batch_ids"])

    selected_batches = [b for b in batch_manifest["batches"] if b.get("type") == "cases" and b["id"] in batch_ids]
    selected_batches = sorted(selected_batches, key=lambda b: int(b["id"]))
    cases_by_id = {c["id"]: c for c in cases}

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    variant_reports: list[dict[str, Any]] = []
    variant_errors: list[dict[str, str]] = []
    for variant in selected_variants:
        print(json.dumps({"event": "variant_start", "variant": variant}, ensure_ascii=False))
        try:
            report = _run_variant(
                variant,
                skill_id=skill_id,
                batches=selected_batches,
                cases_by_id=cases_by_id,
            )
            variant_reports.append(report)
            out_path = out_dir / f"batch_c_{args.run_label}_{variant}.json"
            out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            print(
                json.dumps(
                    {
                        "event": "variant_completed",
                        "variant": variant,
                        "status": "ok",
                        "report": str(out_path),
                    },
                    ensure_ascii=False,
                )
            )
        except Exception as exc:
            variant_errors.append({"variant": variant, "error": str(exc)})
            print(
                json.dumps(
                    {
                        "event": "variant_failed",
                        "variant": variant,
                        "error": str(exc),
                    },
                    ensure_ascii=False,
                )
            )
            if not args.continue_on_error:
                raise

    by_variant = {r["variant"]: r for r in variant_reports}
    full = by_variant.get("full_skill")
    deltas: dict[str, Any] = {}

    if full:
        full_batches = {b["batch_id"]: b for b in full["batches"]}
        for variant in selected_variants:
            if variant == "full_skill":
                continue
            current = by_variant.get(variant)
            if not current:
                continue
            current_batches = {b["batch_id"]: b for b in current["batches"]}
            batch_delta = {}
            for batch_id, full_batch in full_batches.items():
                other = current_batches.get(batch_id)
                if not other:
                    continue
                fsum = full_batch.get("summary", {})
                osum = other.get("summary", {})
                batch_delta[str(batch_id)] = {
                    "delta_pass_rate": round(osum.get("pass_rate", 0.0) - fsum.get("pass_rate", 0.0), 4),
                    "delta_unsafe_proceed_medium_high": osum.get("unsafe_proceed_medium_high", 0)
                    - fsum.get("unsafe_proceed_medium_high", 0),
                    "delta_decision_family_accuracy": round(
                        (osum.get("passed", 0) / max(osum.get("total", 1), 1))
                        - (fsum.get("passed", 0) / max(fsum.get("total", 1), 1)),
                        4,
                    ),
                    "delta_missing_detect_terms_rate": round(
                        osum.get("missing_detect_terms_rate", 0.0)
                        - fsum.get("missing_detect_terms_rate", 0.0),
                        4,
                    ),
                }
            deltas[variant] = batch_delta

    aggregate = {
        "study_id": eval_manifest["study_id"],
        "batch_label": "C",
        "run_label": args.run_label,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "variants": selected_variants,
        "batch_ids": sorted(list(batch_ids)),
        "reports": [f"batch_c_{args.run_label}_{v}.json" for v in selected_variants],
        "variant_errors": variant_errors,
        "kpi_deltas_vs_full_skill": deltas,
    }

    aggregate_path = out_dir / f"batch_c_{args.run_label}_aggregate.json"
    aggregate_path.write_text(json.dumps(aggregate, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        json.dumps(
            {
                "status": "ok" if not variant_errors else "partial",
                "aggregate": str(aggregate_path),
                "variants": selected_variants,
                "variant_errors": variant_errors,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if not variant_errors else 1


if __name__ == "__main__":
    raise SystemExit(main())

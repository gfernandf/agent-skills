import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SKILL_ID = "decision.action-preflight-forecast"
ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = ROOT / "test_inputs" / "action_preflight_minitest_cases.json"
REPORT_PATH = ROOT / "artifacts" / "action_preflight_minitest_report.json"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sdk.embedded import execute_with_meta
from sdk.embedded import _get_components


def _contains_all_terms(payload: Any, terms: list[str]) -> tuple[bool, list[str]]:
    text = json.dumps(payload, ensure_ascii=False).lower()
    missing = [term for term in terms if term.lower() not in text]
    return (len(missing) == 0, missing)


def run() -> int:
    scenarios = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    engine, _, _ = _get_components()
    skill = engine.skill_loader.get_skill(SKILL_ID)
    extract_uncertainty_uses = None
    loaded_uses: list[str] = []
    for step in skill.steps:
        loaded_uses.append(getattr(step, "uses", ""))
        if getattr(step, "id", None) == "extract_uncertainties":
            extract_uncertainty_uses = getattr(step, "uses", None)

    case_limit_raw = os.environ.get("MINITEST_LIMIT_CASES")
    try:
        case_limit = int(case_limit_raw) if case_limit_raw else 0
    except ValueError:
        case_limit = 0
    if case_limit > 0:
        scenarios = scenarios[:case_limit]

    results: list[dict[str, Any]] = []
    pass_count = 0

    def _write_report() -> None:
        report = {
            "skill_id": SKILL_ID,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "loaded_skill_version": getattr(skill, "version", None),
            "loaded_extract_uncertainties_uses": extract_uncertainty_uses,
            "loaded_has_policy_risk_classify": "policy.risk.classify" in loaded_uses,
            "loaded_has_policy_risk_score": "policy.risk.score" in loaded_uses,
            "fixture": str(FIXTURE_PATH),
            "total_cases": len(scenarios),
            "passed_cases": pass_count,
            "pass_rate": round(pass_count / max(len(scenarios), 1), 4),
            "results": results,
        }
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    for scenario in scenarios:
        case_id = scenario["id"]
        inputs = {
            "candidate_action": scenario["candidate_action"],
            "intended_goal": scenario["intended_goal"],
            "context": scenario.get("context", {}),
            "known_constraints": scenario.get("known_constraints", []),
            "available_evidence": scenario.get("available_evidence", []),
            "risk_tolerance": scenario.get("risk_tolerance", "medium"),
        }

        case_result: dict[str, Any] = {
            "id": case_id,
            "risk_band": scenario.get("risk_band", "unknown"),
            "status": "failed",
        }

        try:
            execution = execute_with_meta(
                SKILL_ID,
                inputs,
                channel="minitest",
                tenant_id="tenant-local",
            )
            outputs = execution.get("outputs", {})
            meta = execution.get("meta", {})
            decision_obj = outputs.get("continuation_decision", {})
            decision = decision_obj.get("decision")

            in_family = decision in scenario.get("expected_decision_family", [])
            forbidden_hit = decision in scenario.get("forbidden_decisions", [])
            detects_ok, missing_terms = _contains_all_terms(outputs, scenario.get("must_detect", []))

            case_pass = in_family and (not forbidden_hit) and detects_ok

            case_result.update(
                {
                    "status": "passed" if case_pass else "failed",
                    "decision": decision,
                    "expected_decision_family": scenario.get("expected_decision_family", []),
                    "forbidden_decisions": scenario.get("forbidden_decisions", []),
                    "decision_in_family": in_family,
                    "forbidden_decision_hit": forbidden_hit,
                    "must_detect": scenario.get("must_detect", []),
                    "missing_detect_terms": missing_terms,
                    "output_keys": sorted(list(outputs.keys())),
                    "execution_health": meta.get("execution_health"),
                    "fallback_used": meta.get("fallback_used"),
                }
            )

            if case_pass:
                pass_count += 1

        except Exception as exc:
            case_result.update(
                {
                    "status": "error",
                    "error": str(exc),
                }
            )

        results.append(case_result)

        # Persist after each scenario so long-running jobs are observable.
        _write_report()

    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))

    print(json.dumps({
        "total_cases": report["total_cases"],
        "passed_cases": report["passed_cases"],
        "pass_rate": report["pass_rate"],
        "report": str(REPORT_PATH),
    }, ensure_ascii=False, indent=2))

    return 0 if pass_count == len(scenarios) else 1


if __name__ == "__main__":
    raise SystemExit(run())

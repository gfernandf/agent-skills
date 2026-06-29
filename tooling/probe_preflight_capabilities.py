import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sdk.embedded import execute_capability

PROBES = [
    {
        "id": "reasoning.output.classify",
        "inputs": {
            "output": {"risk_score": 0.72, "risk_safe": False, "dimension_scores": {"impact": 0.8}},
            "categories": ["low", "medium", "high", "critical"],
            "context": "Classify risk level from score and dimensions",
        },
        "required": ["category", "confidence", "rationale"],
    },
    {
        "id": "evaluation.hypothesis.evaluate",
        "inputs": {
            "hypotheses": [
                {"id": "h1", "statement": "Action succeeds with low impact"},
                {"id": "h2", "statement": "Action causes production degradation"},
            ],
            "evidence": [{"id": "e1", "content": "No incidents in last run"}],
            "criteria": [{"name": "support", "weight": 0.6}, {"name": "risk", "weight": 0.4}],
        },
        "required": ["evaluated_hypotheses", "evaluation_summary"],
    },
    {
        "id": "reasoning.uncertainty.extract",
        "inputs": {
            "target": {"candidate_action": {"type": "change"}, "context": {"scope": "unknown"}},
            "context": "Assess uncertainty for this action",
        },
        "required": ["uncertainties"],
    },
    {
        "id": "evaluation.uncertainty.score",
        "inputs": {
            "uncertainties": [
                {"id": "u1", "description": "Rollback not validated"},
                {"id": "u2", "description": "Scope ambiguous"},
            ],
            "scoring_criteria": [{"name": "impact", "weight": 0.5}, {"name": "confidence_gap", "weight": 0.5}],
        },
        "required": ["scored_uncertainties"],
    },
    {
        "id": "policy.risk.classify",
        "inputs": {
            "action": {"type": "patch_production", "target": "gateway"},
            "categories": ["low", "medium", "high", "critical"],
        },
        "required": ["risk_level", "factors", "rationale"],
    },
]


def run_probe(item):
    cap_id = item["id"]
    required = item["required"]
    try:
        out = execute_capability(cap_id, item["inputs"])
        missing = [k for k in required if k not in out]
        return {
            "capability": cap_id,
            "ok": len(missing) == 0,
            "output_keys": sorted(list(out.keys())),
            "missing_required": missing,
            "outputs": out,
        }
    except Exception as exc:
        return {
            "capability": cap_id,
            "ok": False,
            "error": str(exc),
        }


def main():
    results = [run_probe(item) for item in PROBES]
    report = {
        "results": results,
        "summary": {
            "total": len(results),
            "ok": sum(1 for r in results if r.get("ok")),
            "failed": sum(1 for r in results if not r.get("ok")),
        },
    }
    out_path = ROOT / "artifacts" / "preflight_capability_probe_report.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"report": str(out_path), **report["summary"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

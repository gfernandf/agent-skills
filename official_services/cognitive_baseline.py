"""
Cognitive baseline service module.
Provides deterministic Python fallbacks for cognitive capability bindings.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any


CAPABILITY_SPECS: dict[str, dict[str, Any]] = {
    "decision_input_route": {
        "capability": "decision.input.route",
        "outputs": {"route": "string", "confidence": "number"},
    },
    "decision_option_select": {
        "capability": "decision.option.select",
        "outputs": {
            "selected_option": "object",
            "selection_rationale": "string",
            "rejected_options": "array",
            "selection_confidence": "number",
        },
    },
    "decision_strategy_select": {
        "capability": "decision.strategy.select",
        "outputs": {
            "selected_strategy": "object",
            "rejected_strategies": "array",
            "selection_confidence": "number",
        },
    },
    "decision_uncertainty_prioritize": {
        "capability": "decision.uncertainty.prioritize",
        "outputs": {
            "prioritized_uncertainties": "array",
            "next_actions": "array",
            "prioritization_summary": "string",
        },
    },
    "evaluation_assumption_validate": {
        "capability": "evaluation.assumption.validate",
        "outputs": {"validated_assumptions": "array", "confidence_summary": "string"},
    },
    "evaluation_constraint_validate": {
        "capability": "evaluation.constraint.validate",
        "outputs": {
            "validation_result": "object",
            "violations": "array",
            "satisfied_constraints": "array",
        },
    },
    "evaluation_failure_analyze": {
        "capability": "evaluation.failure.analyze",
        "outputs": {
            "root_causes": "array",
            "failure_class": "string",
            "recurrence_risk": "number",
        },
    },
    "evaluation_framework_detect": {
        "capability": "evaluation.framework.detect",
        "outputs": {
            "missing_capabilities": "array",
            "missing_skills": "array",
            "gap_severity": "string",
        },
    },
    "evaluation_framework_rank": {
        "capability": "evaluation.framework.rank",
        "outputs": {"ranked_skills": "array", "ranked_capabilities": "array"},
    },
    "evaluation_hypothesis_compare": {
        "capability": "evaluation.hypothesis.compare",
        "outputs": {
            "ranked_hypotheses": "array",
            "tradeoffs": "array",
            "recommendation": "object",
        },
    },
    "evaluation_hypothesis_evaluate": {
        "capability": "evaluation.hypothesis.evaluate",
        "outputs": {
            "evaluated_hypotheses": "array",
            "evaluation_summary": "string",
            "evidence_gaps": "array",
        },
    },
    "evaluation_option_score": {
        "capability": "evaluation.option.score",
        "outputs": {
            "scored_options": "array",
            "criteria_used": "array",
            "comparative_summary": "string",
            "tradeoffs": "array",
        },
    },
    "evaluation_output_score": {
        "capability": "evaluation.output.score",
        "outputs": {
            "score": "number",
            "dimensions": "object",
            "quality_level": "string",
        },
    },
    "evaluation_output_validate": {
        "capability": "evaluation.output.validate",
        "outputs": {"evaluation": "object"},
    },
    "evaluation_plan_gate": {
        "capability": "evaluation.plan.gate",
        "outputs": {"authorization_result": "object"},
    },
    "evaluation_plan_validate": {
        "capability": "evaluation.plan.validate",
        "outputs": {"validation_result": "object"},
    },
    "evaluation_response_score": {
        "capability": "evaluation.response.score",
        "outputs": {"scores": "object", "overall": "number", "rationale": "string"},
    },
    "evaluation_response_validate": {
        "capability": "evaluation.response.validate",
        "outputs": {
            "valid": "boolean",
            "issues": "array",
            "confidence_adjustment": "number",
            "rationale": "string",
        },
    },
    "evaluation_risk_score": {
        "capability": "evaluation.risk.score",
        "outputs": {
            "risk_score": "number",
            "dimension_scores": "object",
            "flags": "array",
            "safe": "boolean",
        },
    },
    "evaluation_uncertainty_score": {
        "capability": "evaluation.uncertainty.score",
        "outputs": {"scored_uncertainties": "array", "scoring_summary": "string"},
    },
    "evidence_citation_generate": {
        "capability": "evidence.citation.generate",
        "outputs": {"citation": "object"},
    },
    "evidence_claim_verify": {
        "capability": "evidence.claim.verify",
        "outputs": {"verified": "boolean", "evidence": "array", "rationale": "string"},
    },
    "evidence_conflict_detect": {
        "capability": "evidence.conflict.detect",
        "outputs": {"conflicts": "array", "conflict_severity": "string"},
    },
    "evidence_gap_detect": {
        "capability": "evidence.gap.detect",
        "outputs": {"evidence_gaps": "array", "gap_severity": "string"},
    },
    "evidence_source_assess": {
        "capability": "evidence.source.assess",
        "outputs": {"source_scores": "array", "assessment_summary": "string"},
    },
    "evidence_trace_analyze": {
        "capability": "evidence.trace.analyze",
        "outputs": {
            "trace_session_id": "string",
            "updated_trace_state": "object",
            "state_checksum": "string",
            "trace_version": "string",
            "decision_graph": "object",
            "assumptions": "array",
            "alternative_paths": "array",
            "confidence": "number",
            "risk_candidates": "array",
            "summary": "string",
        },
    },
    "evidence_trace_summarize": {
        "capability": "evidence.trace.summarize",
        "outputs": {"trace_summary": "object"},
    },
    "memory_context_compress": {
        "capability": "memory.context.compress",
        "outputs": {"summary_context": "object", "summary_notes": "string"},
    },
    "memory_context_reconcile": {
        "capability": "memory.context.reconcile",
        "outputs": {"reconciled_context": "object", "conflicts": "array"},
    },
    "memory_context_retrieve": {
        "capability": "memory.context.retrieve",
        "outputs": {
            "context": "object",
            "found": "boolean",
            "freshness_hint": "string",
        },
    },
    "memory_context_store": {
        "capability": "memory.context.store",
        "outputs": {"stored": "boolean", "context_id": "string"},
    },
    "memory_context_update": {
        "capability": "memory.context.update",
        "outputs": {"updated": "boolean", "context_id": "string"},
    },
    "perception_content_extract": {
        "capability": "perception.content.extract",
        "outputs": {"text": "string"},
    },
    "perception_entity_extract": {
        "capability": "perception.entity.extract",
        "outputs": {"entities": "array"},
    },
    "perception_input_structure": {
        "capability": "perception.input.structure",
        "outputs": {
            "structured_input": "object",
            "complete": "boolean",
            "missing_fields": "array",
        },
    },
    "perception_keyword_extract": {
        "capability": "perception.keyword.extract",
        "outputs": {"keywords": "array"},
    },
    "perception_language_detect": {
        "capability": "perception.language.detect",
        "outputs": {"language": "string", "confidence": "number"},
    },
    "reasoning_assumption_extract": {
        "capability": "reasoning.assumption.extract",
        "outputs": {"assumptions": "array", "extraction_notes": "string"},
    },
    "reasoning_constraint_extract": {
        "capability": "reasoning.constraint.extract",
        "outputs": {"constraints": "array", "gaps": "array"},
    },
    "reasoning_constraint_reconcile": {
        "capability": "reasoning.constraint.reconcile",
        "outputs": {"reconciled_constraints": "array", "tradeoffs": "array"},
    },
    "reasoning_content_classify": {
        "capability": "reasoning.content.classify",
        "outputs": {"label": "string", "confidence": "number"},
    },
    "reasoning_content_compare": {
        "capability": "reasoning.content.compare",
        "outputs": {
            "similarity": "number",
            "differences": "array",
            "summary": "string",
        },
    },
    "reasoning_content_generate": {
        "capability": "reasoning.content.generate",
        "outputs": {"text": "string"},
    },
    "reasoning_content_merge": {
        "capability": "reasoning.content.merge",
        "outputs": {"text": "string", "item_count": "number"},
    },
    "reasoning_content_summarize": {
        "capability": "reasoning.content.summarize",
        "outputs": {"summary": "string"},
    },
    "reasoning_content_template": {
        "capability": "reasoning.content.template",
        "outputs": {"text": "string"},
    },
    "reasoning_content_transform": {
        "capability": "reasoning.content.transform",
        "outputs": {"text": "string"},
    },
    "reasoning_content_translate": {
        "capability": "reasoning.content.translate",
        "outputs": {"translation": "string"},
    },
    "reasoning_criteria_define": {
        "capability": "reasoning.criteria.define",
        "outputs": {
            "success_criteria": "array",
            "quality_criteria": "array",
            "acceptance_criteria": "array",
        },
    },
    "reasoning_embedding_generate": {
        "capability": "reasoning.embedding.generate",
        "outputs": {"embedding": "array", "model": "string"},
    },
    "reasoning_goal_interpret": {
        "capability": "reasoning.goal.interpret",
        "outputs": {"interpreted_goal": "object", "requires_clarification": "boolean"},
    },
    "reasoning_hypothesis_generate": {
        "capability": "reasoning.hypothesis.generate",
        "outputs": {"hypotheses": "array", "generation_notes": "string"},
    },
    "reasoning_option_analyze": {
        "capability": "reasoning.option.analyze",
        "outputs": {"analyzed_options": "array", "analysis_notes": "string"},
    },
    "reasoning_option_generate": {
        "capability": "reasoning.option.generate",
        "outputs": {"options": "array", "generation_notes": "string"},
    },
    "reasoning_output_classify": {
        "capability": "reasoning.output.classify",
        "outputs": {
            "category": "string",
            "confidence": "number",
            "rationale": "string",
        },
    },
    "reasoning_output_generate": {
        "capability": "reasoning.output.generate",
        "outputs": {"output": "object", "warnings": "array", "coverage": "object"},
    },
    "reasoning_output_normalize": {
        "capability": "reasoning.output.normalize",
        "outputs": {
            "sanitized_output": "object",
            "removals": "array",
            "clean": "boolean",
        },
    },
    "reasoning_output_synthesize": {
        "capability": "reasoning.output.synthesize",
        "outputs": {"candidate_skill": "object", "confidence": "number"},
    },
    "reasoning_plan_decompose": {
        "capability": "reasoning.plan.decompose",
        "outputs": {"expanded_steps": "array", "step_count": "number"},
    },
    "reasoning_plan_generate": {
        "capability": "reasoning.plan.generate",
        "outputs": {"plan": "object", "step_count": "number"},
    },
    "reasoning_plan_map": {
        "capability": "reasoning.plan.map",
        "outputs": {"bound_steps": "array", "unresolved_bindings": "array"},
    },
    "reasoning_plan_reconcile": {
        "capability": "reasoning.plan.reconcile",
        "outputs": {
            "repaired_plan": "object",
            "repair_notes": "array",
            "still_invalid": "boolean",
        },
    },
    "reasoning_plan_synthesize": {
        "capability": "reasoning.plan.synthesize",
        "outputs": {
            "compiled_plan": "object",
            "step_count": "number",
            "compiled_plan_json": "string",
        },
    },
    "reasoning_priority_classify": {
        "capability": "reasoning.priority.classify",
        "outputs": {
            "priority": "string",
            "confidence": "number",
            "rationale": "string",
        },
    },
    "reasoning_problem_decompose": {
        "capability": "reasoning.problem.decompose",
        "outputs": {
            "components": "array",
            "gaps": "array",
            "overlaps": "array",
            "decomposition_notes": "string",
        },
    },
    "reasoning_request_normalize": {
        "capability": "reasoning.request.normalize",
        "outputs": {"normalized_request": "object", "language": "string"},
    },
    "reasoning_response_extract": {
        "capability": "reasoning.response.extract",
        "outputs": {"answer": "string", "confidence": "number"},
    },
    "reasoning_response_generate": {
        "capability": "reasoning.response.generate",
        "outputs": {"report": "object", "report_status": "string"},
    },
    "reasoning_risk_extract": {
        "capability": "reasoning.risk.extract",
        "outputs": {
            "risks": "array",
            "assumptions": "array",
            "failure_modes": "array",
            "mitigation_ideas": "array",
            "extraction_notes": "string",
        },
    },
    "reasoning_sentiment_analyze": {
        "capability": "reasoning.sentiment.analyze",
        "outputs": {
            "sentiment": "string",
            "score": "number",
            "dimensions": "object",
            "rationale": "string",
        },
    },
    "reasoning_theme_cluster": {
        "capability": "reasoning.theme.cluster",
        "outputs": {
            "clusters": "array",
            "unclustered": "array",
            "cluster_quality": "object",
        },
    },
    "reasoning_uncertainty_extract": {
        "capability": "reasoning.uncertainty.extract",
        "outputs": {
            "uncertainties": "array",
            "clarification_questions": "array",
            "extraction_notes": "string",
        },
    },
}


_MEMORY_CONTEXT_DB: dict[str, dict[str, Any]] = {}


def _to_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list)):
        try:
            return json.dumps(value, ensure_ascii=False)
        except Exception:
            return str(value)
    return "" if value is None else str(value)


def _hash_score(seed: str) -> float:
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return round((int(digest[:8], 16) % 100) / 100.0, 2)


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _slug(text: str, prefix: str = "item") -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    if not cleaned:
        return prefix
    return cleaned[:32]


def _pick_first(*values: Any, default: Any = None) -> Any:
    for value in values:
        if value not in (None, "", [], {}):
            return value
    return default


def _collect_text_chunks(kwargs: dict[str, Any]) -> list[str]:
    chunks: list[str] = []
    for value in kwargs.values():
        if isinstance(value, str) and value.strip():
            chunks.append(value.strip())
        elif isinstance(value, dict):
            for sub in value.values():
                if isinstance(sub, str) and sub.strip():
                    chunks.append(sub.strip())
        elif isinstance(value, list):
            for item in value[:5]:
                if isinstance(item, str) and item.strip():
                    chunks.append(item.strip())
                elif isinstance(item, dict):
                    for sub in item.values():
                        if isinstance(sub, str) and sub.strip():
                            chunks.append(sub.strip())
    return chunks


def _ensure_non_empty_array(value: list[Any], fallback_item: Any) -> list[Any]:
    return value if value else [fallback_item]


def _perception_input_structure(**kwargs: Any) -> dict[str, Any]:
    fields = kwargs.get("fields") or []
    raw_input = (
        kwargs.get("raw_input") if isinstance(kwargs.get("raw_input"), dict) else {}
    )
    structured = {}
    missing = []

    for f in fields:
        if not isinstance(f, dict):
            continue
        name = f.get("name")
        required = bool(f.get("required", False))
        default = f.get("default")
        if not isinstance(name, str) or not name:
            continue
        if name in raw_input:
            structured[name] = raw_input[name]
        elif default is not None:
            structured[name] = default
        else:
            if required:
                missing.append(name)
                structured[name] = f"missing:{name}"

    return {
        "structured_input": structured,
        "complete": len(missing) == 0,
        "missing_fields": missing,
    }


def _reasoning_goal_interpret(**kwargs: Any) -> dict[str, Any]:
    nr = kwargs.get("normalized_request")
    objective = "Define and execute the requested task."
    if isinstance(nr, dict):
        raw = nr.get("raw_request") or nr.get("request") or nr.get("text")
        if isinstance(raw, str) and raw.strip():
            objective = raw.strip()
    elif isinstance(nr, str) and nr.strip():
        objective = nr.strip()

    interpreted = {
        "objective": objective,
        "deliverable_type": "analysis_report",
        "success_criteria": [
            "Output addresses the objective directly",
            "Output is internally consistent",
        ],
        "constraints": [],
        "assumptions": [],
        "open_questions": [],
    }
    return {"interpreted_goal": interpreted, "requires_clarification": False}


def _decision_input_route(**kwargs: Any) -> dict[str, Any]:
    query = _to_text(kwargs.get("query") or kwargs.get("user_message") or "")
    low = query.lower()
    agents_raw = kwargs.get("agents")
    agents = []
    if isinstance(agents_raw, list):
        for item in agents_raw:
            if isinstance(item, str) and item.strip():
                agents.append(item.strip())

    if any(token in low for token in ("riesgo", "risk", "seguridad", "security")):
        route = "evaluation.risk.score"
    elif any(token in low for token in ("plan", "roadmap", "pasos", "steps")):
        route = "reasoning.plan.generate"
    elif any(
        token in low for token in ("resumen", "summary", "sintetiza", "summarize")
    ):
        route = "reasoning.content.summarize"
    else:
        route = "reasoning.request.normalize"

    if agents:
        agent_lows = [a.lower() for a in agents]
        chosen = None

        for idx, name in enumerate(agent_lows):
            if name and name in low:
                chosen = agents[idx]
                break

        if chosen is None:
            if any(tok in route for tok in ("summarize", "summary")):
                for idx, name in enumerate(agent_lows):
                    if any(tok in name for tok in ("summar", "resum")):
                        chosen = agents[idx]
                        break
            elif "risk" in route:
                for idx, name in enumerate(agent_lows):
                    if any(tok in name for tok in ("risk", "segur", "safety")):
                        chosen = agents[idx]
                        break
            elif "plan" in route:
                for idx, name in enumerate(agent_lows):
                    if any(tok in name for tok in ("plan", "planner")):
                        chosen = agents[idx]
                        break

        if chosen is None and route in agents:
            chosen = route

        if chosen is None:
            chosen = agents[0]

        route = chosen

    confidence = round(max(0.55, _hash_score(route + low)), 2)
    return {
        "route": route,
        "confidence": confidence,
    }


def _reasoning_option_generate(**kwargs: Any) -> dict[str, Any]:
    goal = _to_text(kwargs.get("goal") or "the stated goal")
    options = [
        {
            "id": "option_1",
            "label": "Conservative",
            "description": f"Lower-risk path for: {goal}",
        },
        {
            "id": "option_2",
            "label": "Balanced",
            "description": f"Balanced trade-off path for: {goal}",
        },
        {
            "id": "option_3",
            "label": "Aggressive",
            "description": f"Higher-upside path for: {goal}",
        },
    ]
    notes = "Options generated with diversified risk/return profiles for downstream scoring and selection."
    return {"options": options, "generation_notes": notes}


def _evaluation_option_score(**kwargs: Any) -> dict[str, Any]:
    options = kwargs.get("options") if isinstance(kwargs.get("options"), list) else []
    criteria = (
        kwargs.get("criteria") if isinstance(kwargs.get("criteria"), list) else []
    )
    if not criteria:
        criteria = [
            {"name": "feasibility", "description": "Ease of execution", "weight": 1.0},
            {"name": "impact", "description": "Expected value", "weight": 1.0},
            {"name": "risk", "description": "Downside exposure", "weight": 1.0},
        ]

    criterion_names: list[str] = []
    for i, c in enumerate(criteria):
        if isinstance(c, dict):
            name = c.get("name")
            criterion_names.append(
                str(name)
                if isinstance(name, str) and name.strip()
                else f"criterion_{i + 1}"
            )
        elif isinstance(c, str) and c.strip():
            criterion_names.append(c.strip())
        else:
            criterion_names.append(f"criterion_{i + 1}")

    scored = []
    for idx, opt in enumerate(options):
        oid = opt.get("id") if isinstance(opt, dict) else f"option_{idx + 1}"
        label = opt.get("label") if isinstance(opt, dict) else str(opt)
        seed = f"{oid}|{label}|{idx}"
        overall = _hash_score(seed)
        per = {
            criterion_names[i]: _hash_score(seed + str(i))
            for i, _ in enumerate(criteria)
        }
        scored.append(
            {
                "option_id": oid,
                "overall_score": overall,
                "per_criterion_scores": per,
                "strengths": ["Aligned with goal"],
                "weaknesses": ["Requires validation"],
            }
        )

    scored.sort(key=lambda x: x.get("overall_score", 0.0), reverse=True)
    joined_criteria = ", ".join(criterion_names[:4]) if criterion_names else "criteria"
    summary = f"Scoring completed with deterministic multi-criteria baseline logic over {joined_criteria}."
    tradeoffs = [
        "Top option shows strongest blended performance under current criteria weights."
    ]
    return {
        "scored_options": scored,
        "criteria_used": criteria,
        "comparative_summary": summary,
        "tradeoffs": tradeoffs,
    }


def _evaluation_output_score(**kwargs: Any) -> dict[str, Any]:
    output = _as_dict(kwargs.get("output"))
    rubric = _as_dict(kwargs.get("rubric"))

    if not output:
        score = 0.0
        dimensions = {
            "coverage": {
                "score": 0.0,
                "rationale": "No structured output provided for evaluation.",
            }
        }
    else:
        total_fields = max(len(output), 1)
        non_empty = sum(1 for v in output.values() if v not in (None, "", [], {}))
        coverage = non_empty / total_fields

        shallow_penalty = 0.0
        for value in output.values():
            if isinstance(value, list) and len(value) == 0:
                shallow_penalty += 1.0
            elif isinstance(value, str) and 0 < len(value.strip()) < 50:
                shallow_penalty += 0.5

        depth = max(0.0, 1.0 - (shallow_penalty / total_fields))
        coherence = round(min(1.0, max(0.0, (coverage + depth) / 2)), 2)

        score = round((coverage + depth + coherence) / 3, 2)

        default_dimensions = {
            "coverage": {
                "score": round(coverage, 2),
                "rationale": "Fraction of non-empty required decision fields.",
            },
            "depth": {
                "score": round(depth, 2),
                "rationale": "Penalizes shallow content such as empty arrays or short strings.",
            },
            "coherence": {
                "score": coherence,
                "rationale": "Consistency estimate derived from coverage/depth balance.",
            },
        }

        if isinstance(rubric.get("dimensions"), dict) and rubric["dimensions"]:
            dimensions = {
                name: default_dimensions.get(
                    name,
                    {
                        "score": score,
                        "rationale": "Rubric dimension scored by baseline aggregate.",
                    },
                )
                for name in rubric["dimensions"].keys()
                if isinstance(name, str) and name
            }
            if not dimensions:
                dimensions = default_dimensions
        else:
            dimensions = default_dimensions

    if score >= 0.9:
        quality_level = "excellent"
    elif score >= 0.7:
        quality_level = "good"
    elif score >= 0.5:
        quality_level = "fair"
    else:
        quality_level = "poor"

    return {
        "score": score,
        "dimensions": dimensions,
        "quality_level": quality_level,
    }


def _decision_option_select(**kwargs: Any) -> dict[str, Any]:
    options = kwargs.get("options") if isinstance(kwargs.get("options"), list) else []
    scores = (
        kwargs.get("option_scores")
        if isinstance(kwargs.get("option_scores"), list)
        else []
    )

    selected = None
    if scores:
        best = max(
            scores,
            key=lambda x: x.get("overall_score", 0.0) if isinstance(x, dict) else 0.0,
        )
        best_id = best.get("option_id") if isinstance(best, dict) else None
        if best_id is not None:
            for opt in options:
                if isinstance(opt, dict) and opt.get("id") == best_id:
                    selected = opt
                    break
    if selected is None and options:
        selected = (
            options[0]
            if isinstance(options[0], dict)
            else {"id": "option_1", "label": str(options[0])}
        )
    if selected is None:
        selected = {"id": "option_1", "label": "Default Option"}

    rejected = []
    for opt in options:
        if isinstance(opt, dict) and opt.get("id") != selected.get("id"):
            rejected.append(
                {
                    "option": opt.get("id"),
                    "reason": "Lower overall score under current criteria",
                }
            )

    return {
        "selected_option": selected,
        "selection_rationale": "Selected by highest available overall score.",
        "rejected_options": rejected,
        "selection_confidence": 0.62,
    }


def _decision_uncertainty_prioritize(**kwargs: Any) -> dict[str, Any]:
    scored = _as_list(kwargs.get("scored_uncertainties"))
    capacity = int(kwargs.get("capacity_limit", 3) or 3)
    ranked: list[dict[str, Any]] = []

    for idx, u in enumerate(scored):
        uobj = _as_dict(u)
        uid = _pick_first(
            uobj.get("uncertainty_id"), uobj.get("id"), default=f"u{idx + 1}"
        )
        score = float(uobj.get("overall_score", uobj.get("impact_score", 0.5)))
        ranked.append(
            {
                "rank": idx + 1,
                "uncertainty_id": uid,
                "overall_score": round(score, 2),
                "rationale": "Higher impact and lower evidence confidence require earlier mitigation.",
            }
        )

    ranked.sort(key=lambda x: x.get("overall_score", 0.0), reverse=True)
    ranked = ranked[: max(1, capacity)]
    actions = [
        {
            "uncertainty_id": item["uncertainty_id"],
            "action": "Collect one validating signal and one falsifying signal.",
            "owner_hint": "domain-lead",
        }
        for item in ranked
    ]
    return {
        "prioritized_uncertainties": _ensure_non_empty_array(
            ranked,
            {
                "rank": 1,
                "uncertainty_id": "u1",
                "overall_score": 0.6,
                "rationale": "Default prioritization when uncertainty evidence is sparse.",
            },
        ),
        "next_actions": _ensure_non_empty_array(
            actions,
            {
                "uncertainty_id": "u1",
                "action": "Run a focused clarification interview.",
                "owner_hint": "analyst",
            },
        ),
        "prioritization_summary": "Prioritization emphasizes uncertainties with highest execution impact.",
    }


def _evaluation_assumption_validate(**kwargs: Any) -> dict[str, Any]:
    assumptions = _as_list(kwargs.get("assumptions"))
    validated: list[dict[str, Any]] = []
    for idx, item in enumerate(assumptions):
        obj = _as_dict(item)
        statement = _pick_first(
            obj.get("statement"),
            obj.get("label"),
            obj.get("description"),
            default=f"Assumption {idx + 1}",
        )
        status = "supported" if _hash_score(statement) >= 0.66 else "weak"
        validated.append(
            {
                "id": _pick_first(obj.get("id"), default=f"a{idx + 1}"),
                "statement": statement,
                "status": status,
                "confidence": round(0.72 if status == "supported" else 0.48, 2),
                "rationale": "Validation based on internal consistency and available evidence coverage.",
            }
        )
    validated = _ensure_non_empty_array(
        validated,
        {
            "id": "a1",
            "statement": "Core dependency remains available during execution.",
            "status": "weak",
            "confidence": 0.45,
            "rationale": "No direct evidence provided.",
        },
    )
    return {
        "validated_assumptions": validated,
        "confidence_summary": "Assumptions are partially supported; highest uncertainty remains around external dependencies.",
    }


def _evaluation_failure_analyze(**kwargs: Any) -> dict[str, Any]:
    failure = _to_text(
        kwargs.get("failure") or kwargs.get("incident") or "Observed execution failure"
    )
    root_causes = [
        {
            "id": "rc-1",
            "description": "Constraint mismatch between plan assumptions and runtime context.",
            "confidence": 0.66,
            "evidence": [failure[:180]],
        }
    ]
    return {
        "root_causes": root_causes,
        "failure_class": "execution_alignment_failure",
        "recurrence_risk": 0.58,
    }


def _evaluation_plan_validate(**kwargs: Any) -> dict[str, Any]:
    expanded_plan = _as_dict(kwargs.get("expanded_plan"))
    bound_steps = _as_list(expanded_plan.get("bound_steps"))

    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    if not bound_steps:
        errors.append(
            {
                "step_id": None,
                "check": "plan.non_empty",
                "message": "expanded_plan.bound_steps must contain at least one step.",
            }
        )

    seen_ids: set[str] = set()
    for idx, step in enumerate(bound_steps):
        sobj = _as_dict(step)
        step_id = _pick_first(sobj.get("id"), default=f"step-{idx + 1}")
        step_type = sobj.get("type")
        step_ref = sobj.get("ref")
        outputs = _as_dict(sobj.get("outputs"))

        if step_id in seen_ids:
            errors.append(
                {
                    "step_id": step_id,
                    "check": "step.id.unique",
                    "message": "Duplicate step id detected.",
                }
            )
        seen_ids.add(step_id)

        if step_type not in {"capability", "skill"}:
            errors.append(
                {
                    "step_id": step_id,
                    "check": "step.type.valid",
                    "message": "Step type must be either 'capability' or 'skill'.",
                }
            )

        if not isinstance(step_ref, str) or not step_ref.strip():
            errors.append(
                {
                    "step_id": step_id,
                    "check": "step.ref.present",
                    "message": "Step ref must be a non-empty capability or skill reference.",
                }
            )

        if not outputs:
            warnings.append(
                {
                    "step_id": step_id,
                    "check": "step.outputs.present",
                    "message": "Step has no declared outputs mapping.",
                }
            )

    status = "passed" if not errors else "failed"
    if not warnings:
        warnings.append(
            {
                "step_id": None,
                "check": "validation.summary",
                "message": "Validation completed; review warnings for governance and operability context.",
            }
        )
    repairable = bool(errors) and all(
        e.get("check") != "plan.non_empty" for e in errors
    )

    validation_result = {
        "status": status,
        "errors": errors,
        "warnings": warnings,
        "repairable": repairable,
        "check_count": max(1, len(bound_steps) * 3),
    }

    result: dict[str, Any] = {
        "validation_result": validation_result,
        "validation_errors": errors,
        "validation_warnings": warnings,
        "repairable": repairable,
    }
    if status == "passed":
        result["validated_plan"] = expanded_plan

    return result


def _evaluation_framework_detect(**kwargs: Any) -> dict[str, Any]:
    goal = _to_text(kwargs.get("interpreted_goal") or kwargs.get("goal") or "goal")
    missing_capabilities = [
        {
            "name": "evidence.source.assess",
            "reason": "Goal requires reliability checks for supporting sources.",
            "impact": "high",
        }
    ]
    missing_skills = [
        {
            "name": "agent.plan.generate",
            "reason": "No complete orchestration skill inferred for the requested deliverable.",
            "impact": "medium",
        }
    ]
    severity = "blocking" if "regulator" in goal.lower() else "minor"
    return {
        "missing_capabilities": missing_capabilities,
        "missing_skills": missing_skills,
        "gap_severity": severity,
    }


def _evaluation_framework_rank(**kwargs: Any) -> dict[str, Any]:
    items = _as_list(kwargs.get("candidate_items"))
    ranked_skills = []
    ranked_capabilities = []
    for idx, item in enumerate(items[:5]):
        obj = _as_dict(item)
        ref = _pick_first(
            obj.get("ref"),
            obj.get("id"),
            obj.get("label"),
            default=f"candidate-{idx + 1}",
        )
        base = _hash_score(ref)
        ranked_skills.append(
            {
                "rank": idx + 1,
                "ref": ref,
                "score": base,
                "rationale": "Skill coverage over goal decomposition.",
            }
        )
        ranked_capabilities.append(
            {
                "rank": idx + 1,
                "ref": ref,
                "score": round(max(base - 0.05, 0.0), 2),
                "rationale": "Capability fit against required control points.",
            }
        )

    return {
        "ranked_skills": _ensure_non_empty_array(
            ranked_skills,
            {
                "rank": 1,
                "ref": "agent.plan.generate",
                "score": 0.69,
                "rationale": "Default best candidate.",
            },
        ),
        "ranked_capabilities": _ensure_non_empty_array(
            ranked_capabilities,
            {
                "rank": 1,
                "ref": "reasoning.plan.generate",
                "score": 0.67,
                "rationale": "Default best capability.",
            },
        ),
    }


def _evaluation_hypothesis_evaluate(**kwargs: Any) -> dict[str, Any]:
    hypotheses = _as_list(kwargs.get("hypotheses"))
    evaluated = []
    for idx, h in enumerate(hypotheses):
        obj = _as_dict(h)
        hid = _pick_first(
            obj.get("hypothesis_id"), obj.get("id"), default=f"h{idx + 1}"
        )
        support = round(_hash_score(hid + "support"), 2)
        contradiction = round(max(0.0, 1.0 - support - 0.1), 2)
        status = "supported" if support >= 0.65 else "uncertain"
        evaluated.append(
            {
                "hypothesis_id": hid,
                "support_score": support,
                "contradiction_score": contradiction,
                "status": status,
                "rationale": "Assessment balances supporting signals and contradictory observations.",
            }
        )
    return {
        "evaluated_hypotheses": _ensure_non_empty_array(
            evaluated,
            {
                "hypothesis_id": "h1",
                "support_score": 0.58,
                "contradiction_score": 0.27,
                "status": "uncertain",
                "rationale": "Insufficient direct evidence.",
            },
        ),
        "evaluation_summary": "Hypothesis evaluation completed with explicit support/contradiction balance.",
        "evidence_gaps": [
            {
                "hypothesis_id": "h1",
                "missing_evidence": "counterfactual experiment result",
            }
        ],
    }


def _evaluation_hypothesis_compare(**kwargs: Any) -> dict[str, Any]:
    evaluated = _as_list(kwargs.get("evaluated_hypotheses"))
    ranked = []
    for idx, item in enumerate(evaluated):
        obj = _as_dict(item)
        hid = _pick_first(
            obj.get("hypothesis_id"), obj.get("id"), default=f"h{idx + 1}"
        )
        support = float(obj.get("support_score", 0.5))
        contradiction = float(obj.get("contradiction_score", 0.2))
        score = round(max(support - contradiction * 0.5, 0.0), 2)
        ranked.append(
            {
                "rank": idx + 1,
                "hypothesis_id": hid,
                "score": score,
                "rationale": "Net score derived from support minus contradiction penalty.",
            }
        )
    ranked.sort(key=lambda x: x.get("score", 0.0), reverse=True)
    lead = ranked[0] if ranked else {"hypothesis_id": "h1", "score": 0.55}
    return {
        "ranked_hypotheses": _ensure_non_empty_array(
            ranked,
            {
                "rank": 1,
                "hypothesis_id": "h1",
                "score": 0.55,
                "rationale": "Default lead hypothesis.",
            },
        ),
        "tradeoffs": [
            {
                "between": [lead.get("hypothesis_id"), "h2"],
                "tension": "explanatory_power_vs_scope",
            }
        ],
        "recommendation": {
            "lead_hypothesis": lead.get("hypothesis_id"),
            "confidence": min(0.85, max(0.4, float(lead.get("score", 0.55)))),
            "caveats": ["Collect targeted evidence to reduce residual ambiguity."],
        },
    }


def _evaluation_uncertainty_score(**kwargs: Any) -> dict[str, Any]:
    uncertainties = _as_list(kwargs.get("uncertainties"))
    scored = []
    for idx, item in enumerate(uncertainties):
        obj = _as_dict(item)
        uid = _pick_first(
            obj.get("uncertainty_id"), obj.get("id"), default=f"u{idx + 1}"
        )
        impact = round(_hash_score(uid + "impact"), 2)
        gap = round(_hash_score(uid + "gap"), 2)
        overall = round((impact + gap) / 2, 2)
        scored.append(
            {
                "uncertainty_id": uid,
                "impact_score": impact,
                "confidence_gap_score": gap,
                "overall_score": overall,
            }
        )
    return {
        "scored_uncertainties": _ensure_non_empty_array(
            scored,
            {
                "uncertainty_id": "u1",
                "impact_score": 0.7,
                "confidence_gap_score": 0.6,
                "overall_score": 0.65,
            },
        ),
        "scoring_summary": "Top uncertainties combine high impact with large confidence gaps.",
    }


def _evidence_conflict_detect(**kwargs: Any) -> dict[str, Any]:
    evidence = _as_list(kwargs.get("evidence") or kwargs.get("items"))
    conflict = {
        "id": "conflict-1",
        "items": [
            _pick_first(
                _as_dict(evidence[0]).get("id") if evidence else None, default="e1"
            ),
            _pick_first(
                _as_dict(evidence[1]).get("id") if len(evidence) > 1 else None,
                default="e2",
            ),
        ],
        "rationale": "Claims disagree on causal direction under the same context window.",
    }
    return {"conflicts": [conflict], "conflict_severity": "medium"}


def _evidence_gap_detect(**kwargs: Any) -> dict[str, Any]:
    return {
        "evidence_gaps": [
            {
                "dimension": "counterfactual",
                "missing": "No comparison against baseline scenario.",
                "impact": "medium",
            }
        ],
        "gap_severity": "medium",
    }


def _evidence_source_assess(**kwargs: Any) -> dict[str, Any]:
    sources = _as_list(
        kwargs.get("sources") or kwargs.get("evidence") or kwargs.get("items")
    )
    scores = []
    for idx, src in enumerate(sources[:5]):
        obj = _as_dict(src)
        sid = _pick_first(obj.get("id"), obj.get("source_id"), default=f"s{idx + 1}")
        base = _hash_score(sid)
        scores.append(
            {
                "source_id": sid,
                "credibility": round(base, 2),
                "relevance": round(min(base + 0.1, 1.0), 2),
                "recency": round(max(base - 0.1, 0.0), 2),
                "overall": round(
                    (base + min(base + 0.1, 1.0) + max(base - 0.1, 0.0)) / 3, 2
                ),
            }
        )
    return {
        "source_scores": _ensure_non_empty_array(
            scores,
            {
                "source_id": "s1",
                "credibility": 0.68,
                "relevance": 0.72,
                "recency": 0.61,
                "overall": 0.67,
            },
        ),
        "assessment_summary": "Source quality is moderate; triangulation is recommended before commitment.",
    }


def _perception_entity_extract(**kwargs: Any) -> dict[str, Any]:
    text = " ".join(_collect_text_chunks(kwargs))
    candidates = re.findall(r"\b[A-Z][a-zA-Z0-9_-]{2,}\b", text)
    entities = []
    for idx, token in enumerate(candidates[:5]):
        entities.append(
            {
                "id": f"ent-{idx + 1}",
                "text": token,
                "type": "proper_noun",
                "confidence": 0.63,
            }
        )
    return {
        "entities": _ensure_non_empty_array(
            entities,
            {"id": "ent-1", "text": "Project", "type": "concept", "confidence": 0.55},
        )
    }


def _perception_keyword_extract(**kwargs: Any) -> dict[str, Any]:
    text = " ".join(_collect_text_chunks(kwargs)).lower()
    tokens = [
        t
        for t in re.findall(r"\b[a-záéíóúñ]{4,}\b", text)
        if t not in {"para", "sobre", "entre", "with", "from"}
    ]
    unique = []
    for tok in tokens:
        if tok not in unique:
            unique.append(tok)
    keywords = [
        {"keyword": tok, "weight": round(_hash_score(tok), 2)} for tok in unique[:8]
    ]
    return {
        "keywords": _ensure_non_empty_array(
            keywords, {"keyword": "riesgo", "weight": 0.62}
        )
    }


def _reasoning_assumption_extract(**kwargs: Any) -> dict[str, Any]:
    target = _to_text(kwargs.get("target") or kwargs.get("context") or "target")
    assumptions = [
        {
            "id": "asm-1",
            "statement": "External dependency response times remain within expected SLO.",
            "scope": "execution",
            "fragility_hint": "medium",
            "evidence_anchor": target[:120],
        }
    ]
    return {
        "assumptions": assumptions,
        "extraction_notes": "Assumptions extracted from implicit operational dependencies.",
    }


def _reasoning_constraint_extract(**kwargs: Any) -> dict[str, Any]:
    constraints = _as_list(kwargs.get("constraints"))
    normalized = []
    for idx, c in enumerate(constraints):
        obj = _as_dict(c)
        normalized.append(
            {
                "id": _pick_first(obj.get("id"), default=f"c{idx + 1}"),
                "statement": _pick_first(
                    obj.get("statement"),
                    obj.get("label"),
                    default="Constraint statement",
                ),
                "type": _pick_first(obj.get("type"), default="hard"),
                "source": _pick_first(obj.get("source"), default="input"),
            }
        )
    return {
        "constraints": _ensure_non_empty_array(
            normalized,
            {
                "id": "c1",
                "statement": "Budget cap must not be exceeded.",
                "type": "hard",
                "source": "goal",
            },
        ),
        "gaps": [{"id": "g1", "description": "Missing explicit escalation threshold."}],
    }


def _reasoning_constraint_reconcile(**kwargs: Any) -> dict[str, Any]:
    constraints = _as_list(kwargs.get("constraints"))
    reconciled = []
    for idx, c in enumerate(constraints[:5]):
        obj = _as_dict(c)
        reconciled.append(
            {
                "id": _pick_first(obj.get("id"), default=f"rc{idx + 1}"),
                "statement": _pick_first(obj.get("statement"), default="Constraint"),
                "precedence": idx + 1,
            }
        )
    return {
        "reconciled_constraints": _ensure_non_empty_array(
            reconciled,
            {
                "id": "rc1",
                "statement": "Safety constraints override speed constraints.",
                "precedence": 1,
            },
        ),
        "tradeoffs": [
            {"dimension": "speed_vs_safety", "decision": "prioritize_safety"}
        ],
    }


def _reasoning_content_compare(**kwargs: Any) -> dict[str, Any]:
    a = _to_text(
        _pick_first(
            kwargs.get("text_a"), kwargs.get("left"), kwargs.get("source"), default=""
        )
    )
    b = _to_text(
        _pick_first(
            kwargs.get("text_b"), kwargs.get("right"), kwargs.get("target"), default=""
        )
    )
    sim = round(_hash_score(a + "|" + b), 2)
    return {
        "similarity": sim,
        "differences": [
            {
                "dimension": "evidence_coverage",
                "description": "One text provides stronger causal evidence while the other is more prescriptive.",
                "severity": "moderate",
            }
        ],
        "summary": "Texts are directionally aligned but differ in evidentiary depth and actionability focus.",
    }


def _reasoning_criteria_define(**kwargs: Any) -> dict[str, Any]:
    return {
        "success_criteria": [
            "Recommendation identifies a single primary option with explicit rationale.",
            "Output includes measurable confidence and uncertainty statements.",
        ],
        "quality_criteria": [
            "Reasoning is internally consistent across assumptions and risks.",
            "Evidence references are explicit for major claims.",
        ],
        "acceptance_criteria": [
            "Stakeholder can act on the recommendation without additional decomposition.",
            "Known tradeoffs and next actions are documented.",
        ],
    }


def _reasoning_embedding_generate(**kwargs: Any) -> dict[str, Any]:
    text = _to_text(
        _pick_first(
            kwargs.get("text"), kwargs.get("content"), default="embedding-input"
        )
    )
    emb = [round(_hash_score(f"{text}-{i}"), 4) for i in range(16)]
    return {"embedding": emb, "model": "cognitive_baseline_v1"}


def _reasoning_hypothesis_generate(**kwargs: Any) -> dict[str, Any]:
    goal = _to_text(
        _pick_first(
            kwargs.get("goal"), kwargs.get("problem"), default="the observed issue"
        )
    )
    hypotheses = [
        {
            "id": "h1",
            "statement": f"Primary bottleneck is constraint misalignment affecting {goal[:80]}.",
            "rationale": "Pattern appears when planning assumptions diverge from runtime constraints.",
            "confidence_hint": "medium",
        },
        {
            "id": "h2",
            "statement": f"Secondary bottleneck is evidence sparsity around {goal[:80]}.",
            "rationale": "Limited verification signals increase uncertainty and delay commitment.",
            "confidence_hint": "low",
        },
    ]
    return {
        "hypotheses": hypotheses,
        "generation_notes": "Hypotheses generated from structural failure patterns and evidence coverage.",
    }


def _reasoning_option_analyze(**kwargs: Any) -> dict[str, Any]:
    options = _as_list(kwargs.get("options"))
    analyzed = []
    for idx, opt in enumerate(options[:6]):
        obj = _as_dict(opt)
        oid = _pick_first(obj.get("id"), default=f"opt-{idx + 1}")
        label = _pick_first(obj.get("label"), default=oid)
        analyzed.append(
            {
                "option_id": oid,
                "label": label,
                "pros": [
                    "Fast path to measurable learning.",
                    "Keeps optionality for later scale.",
                ],
                "cons": ["May underdeliver on initial stakeholder expectations."],
                "risks": ["Execution drift if decision criteria are not monitored."],
            }
        )
    return {
        "analyzed_options": _ensure_non_empty_array(
            analyzed,
            {
                "option_id": "opt-1",
                "label": "baseline option",
                "pros": ["Balanced risk and speed."],
                "cons": ["Requires disciplined monitoring."],
                "risks": ["Assumption invalidation."],
            },
        ),
        "analysis_notes": "Analysis emphasizes practical tradeoffs and execution risk exposure.",
    }


def _reasoning_plan_decompose(**kwargs: Any) -> dict[str, Any]:
    expanded = [
        {
            "id": "step-1",
            "type": "capability",
            "ref": "reasoning.option.generate",
            "purpose": "Generate candidate options.",
            "inputs": {"goal": "$state.vars.goal"},
            "outputs": {"options": "$state.vars.options"},
        },
        {
            "id": "step-2",
            "type": "capability",
            "ref": "evaluation.option.score",
            "purpose": "Score generated options.",
            "inputs": {"options": "$state.vars.options", "goal": "$state.vars.goal"},
            "outputs": {"scored_options": "$state.vars.scored_options"},
        },
    ]
    return {"expanded_steps": expanded, "step_count": len(expanded)}


def _reasoning_plan_map(**kwargs: Any) -> dict[str, Any]:
    steps = _as_list(kwargs.get("expanded_steps") or kwargs.get("steps"))
    mapped = []
    for idx, step in enumerate(steps):
        obj = _as_dict(step)
        mapped.append(
            {
                "id": _pick_first(obj.get("id"), default=f"step-{idx + 1}"),
                "type": _pick_first(obj.get("type"), default="capability"),
                "ref": _pick_first(
                    obj.get("ref"), default="reasoning.content.summarize"
                ),
                "purpose": _pick_first(obj.get("purpose"), default="Mapped plan step"),
                "inputs": _pick_first(
                    obj.get("inputs"), default={"input": "$state.vars.input"}
                ),
                "outputs": _pick_first(
                    obj.get("outputs"), default={"result": "$state.vars.result"}
                ),
            }
        )
    return {
        "bound_steps": _ensure_non_empty_array(
            mapped,
            {
                "id": "step-1",
                "type": "capability",
                "ref": "reasoning.plan.generate",
                "purpose": "Generate baseline plan",
                "inputs": {"goal": "$state.vars.goal"},
                "outputs": {"plan": "$state.vars.plan"},
            },
        ),
        "unresolved_bindings": [],
    }


def _reasoning_plan_reconcile(**kwargs: Any) -> dict[str, Any]:
    plan = _as_dict(kwargs.get("plan") or kwargs.get("compiled_plan") or {})
    repaired = dict(plan)
    if "steps" not in repaired:
        repaired["steps"] = [
            {"id": "step-1", "ref": "reasoning.option.generate"},
            {"id": "step-2", "ref": "evaluation.option.score"},
        ]
    return {
        "repaired_plan": repaired,
        "repair_notes": [
            {
                "step_id": "step-1",
                "action": "normalized_ref",
                "original": "option.generate",
                "replacement": "reasoning.option.generate",
            }
        ],
        "still_invalid": False,
    }


def _reasoning_problem_decompose(**kwargs: Any) -> dict[str, Any]:
    goal = _to_text(
        _pick_first(kwargs.get("problem"), kwargs.get("goal"), default="problem")
    )
    components = [
        {
            "id": "scope-definition",
            "label": "Scope Definition",
            "description": f"Define boundaries and success outcomes for: {goal[:80]}",
            "dependencies": [],
        },
        {
            "id": "option-evaluation",
            "label": "Option Evaluation",
            "description": "Score alternatives against explicit criteria and constraints.",
            "dependencies": ["scope-definition"],
        },
    ]
    return {
        "components": components,
        "gaps": [
            {"id": "gap-1", "description": "No explicit escalation threshold defined."}
        ],
        "overlaps": [
            {
                "between": ["scope-definition", "option-evaluation"],
                "risk": "criteria duplication",
            }
        ],
        "decomposition_notes": "Decomposition maximizes traceability from constraints to decisions.",
    }


def _reasoning_response_generate(**kwargs: Any) -> dict[str, Any]:
    goal = _to_text(kwargs.get("goal") or "the task")
    selected = _as_dict(kwargs.get("selected_option"))
    option_label = _pick_first(
        selected.get("label"), selected.get("id"), default="selected option"
    )
    user_response = (
        f"Recomendacion principal: {option_label}.\n\n"
        f"Objetivo atendido: {goal}.\n"
        "Se prioriza una ruta de ejecucion incremental con monitoreo explicito de riesgos."
    )
    report = {
        "user_response": user_response,
        "artifacts": [
            {
                "name": "decision-summary",
                "type": "text/markdown",
                "content": user_response,
            },
            {
                "name": "next-actions",
                "type": "application/json",
                "content": [
                    {"action": "validate assumptions"},
                    {"action": "run pilot"},
                ],
            },
        ],
        "limitations": [
            "Response uses deterministic baseline logic without external retrieval."
        ],
    }
    return {"report": report, "report_status": "success"}


def _reasoning_risk_extract(**kwargs: Any) -> dict[str, Any]:
    risks = [
        {
            "id": "r1",
            "description": "Execution delays due to unresolved cross-team dependencies.",
            "category": "delivery",
            "severity_hint": "high",
            "related_assumptions": ["asm-1"],
        }
    ]
    assumptions = [
        {
            "id": "asm-1",
            "statement": "Critical stakeholders remain available for decision checkpoints.",
            "fragility_hint": "medium",
        }
    ]
    return {
        "risks": risks,
        "assumptions": assumptions,
        "failure_modes": [
            {
                "id": "fm-1",
                "description": "Decision loop stalls after first uncertainty spike.",
                "trigger_conditions": ["No confidence update over two cycles"],
                "related_risks": ["r1"],
            }
        ],
        "mitigation_ideas": [
            {
                "risk_id": "r1",
                "suggestion": "Introduce weekly risk checkpoint",
                "effort_hint": "low",
            }
        ],
        "extraction_notes": "Risk extraction covers operational, evidence, and dependency dimensions.",
    }


def _reasoning_sentiment_analyze(**kwargs: Any) -> dict[str, Any]:
    text = " ".join(_collect_text_chunks(kwargs)).lower()
    positive_hits = sum(
        1 for w in ["good", "mejora", "success", "benefit", "favorable"] if w in text
    )
    negative_hits = sum(
        1 for w in ["risk", "problem", "fallo", "delay", "cost"] if w in text
    )
    polarity = positive_hits - negative_hits
    if polarity > 1:
        sentiment = "positive"
    elif polarity < -1:
        sentiment = "negative"
    elif positive_hits > 0 and negative_hits > 0:
        sentiment = "mixed"
    else:
        sentiment = "neutral"
    score = max(-1.0, min(1.0, round(polarity / 4.0, 2)))
    return {
        "sentiment": sentiment,
        "score": score,
        "dimensions": {
            "risk_tone": {
                "label": "elevated" if negative_hits > positive_hits else "balanced",
                "score": round(
                    max(
                        0.0, min(1.0, 0.5 + negative_hits * 0.1 - positive_hits * 0.05)
                    ),
                    2,
                ),
            },
            "opportunity_tone": {
                "label": "present" if positive_hits > 0 else "limited",
                "score": round(max(0.0, min(1.0, 0.4 + positive_hits * 0.1)), 2),
            },
        },
        "rationale": "Sentiment derived from lexical polarity balance and risk/opportunity cues.",
    }


def _reasoning_theme_cluster(**kwargs: Any) -> dict[str, Any]:
    items = _as_list(
        kwargs.get("items") or kwargs.get("documents") or kwargs.get("evidence")
    )
    ids = []
    for idx, item in enumerate(items):
        obj = _as_dict(item)
        ids.append(_pick_first(obj.get("id"), default=f"item-{idx + 1}"))
    clusters = [
        {
            "theme": "execution_risk",
            "description": "Signals related to delivery and dependency uncertainty.",
            "item_ids": ids[: max(1, len(ids) // 2)] or ["item-1"],
            "summary": "Cluster captures most concerns affecting delivery confidence.",
        },
        {
            "theme": "decision_quality",
            "description": "Signals about evidence quality and recommendation robustness.",
            "item_ids": ids[max(1, len(ids) // 2) :] or ["item-2"],
            "summary": "Cluster captures quality and explainability constraints.",
        },
    ]
    return {
        "clusters": clusters,
        "unclustered": [{"id": "item-x", "reason": "Insufficient semantic context"}],
        "cluster_quality": {
            "coherence_score": 0.68,
            "coverage_ratio": 0.9,
            "overlap_warnings": [],
        },
    }


def _reasoning_uncertainty_extract(**kwargs: Any) -> dict[str, Any]:
    return {
        "uncertainties": [
            {
                "id": "u1",
                "description": "Demand volatility may invalidate the selected rollout cadence.",
                "category": "market",
                "impact_area": "go_to_market",
                "severity_hint": "high",
            }
        ],
        "clarification_questions": [
            "What evidence threshold should trigger strategy pivot?",
            "Which assumptions are owner-verified versus inferred?",
        ],
        "extraction_notes": "Uncertainty extraction prioritizes variables with high decision sensitivity.",
    }


def _memory_context_store(**kwargs: Any) -> dict[str, Any]:
    context_id = _to_text(
        kwargs.get("context_id")
        or f"ctx-{_slug(_to_text(kwargs.get('scope') or 'default'))}"
    )
    context = _as_dict(kwargs.get("context"))
    if not context:
        context = {"note": "empty_context", "source": "deterministic_baseline"}
    _MEMORY_CONTEXT_DB[context_id] = dict(context)
    return {"stored": True, "context_id": context_id}


def _memory_context_retrieve(**kwargs: Any) -> dict[str, Any]:
    context_id = _to_text(kwargs.get("context_id") or "")
    found = context_id in _MEMORY_CONTEXT_DB
    context = dict(_MEMORY_CONTEXT_DB.get(context_id, {}))
    freshness = "fresh" if found else "missing"
    return {
        "context": context
        if context
        else {"context_id": context_id, "status": "not_found"},
        "found": found,
        "freshness_hint": freshness,
    }


def _memory_context_update(**kwargs: Any) -> dict[str, Any]:
    context_id = _to_text(kwargs.get("context_id") or "")
    patch = _as_dict(
        _pick_first(kwargs.get("patch"), kwargs.get("context_delta"), default={})
    )
    if context_id not in _MEMORY_CONTEXT_DB:
        _MEMORY_CONTEXT_DB[context_id] = {}
    _MEMORY_CONTEXT_DB[context_id].update(patch)
    return {"updated": True, "context_id": context_id}


def _memory_context_reconcile(**kwargs: Any) -> dict[str, Any]:
    contexts = _as_list(kwargs.get("contexts"))
    reconciled: dict[str, Any] = {}
    conflicts: list[dict[str, Any]] = []
    for idx, item in enumerate(contexts):
        obj = _as_dict(item)
        for key, value in obj.items():
            if key in reconciled and reconciled[key] != value:
                conflicts.append(
                    {
                        "field": key,
                        "left": reconciled[key],
                        "right": value,
                        "source_index": idx,
                    }
                )
            reconciled[key] = value
    if not reconciled:
        reconciled = {"status": "no_contexts", "source": "deterministic_baseline"}
    return {"reconciled_context": reconciled, "conflicts": conflicts}


def _memory_context_compress(**kwargs: Any) -> dict[str, Any]:
    context = _as_dict(kwargs.get("context"))
    keys = sorted(context.keys())
    summary_context = {
        "key_count": len(keys),
        "keys": keys[:10],
        "preview": {k: context[k] for k in keys[:3]},
    }
    notes = (
        f"Compressed context with {len(keys)} keys for downstream retrieval efficiency."
    )
    return {"summary_context": summary_context, "summary_notes": notes}


def _generic_capability(operation: str, **kwargs: Any) -> dict[str, Any]:
    spec = CAPABILITY_SPECS.get(operation)
    if not spec:
        return {"result": kwargs}

    capability_id = spec["capability"]
    outputs = spec.get("outputs", {})

    result: dict[str, Any] = {}
    for name, otype in outputs.items():
        if name in kwargs:
            result[name] = kwargs[name]
            continue

        if otype == "string":
            if (
                "summary" in name
                or "rationale" in name
                or "notes" in name
                or "explanation" in name
            ):
                source_text = _to_text(
                    _pick_first(
                        kwargs.get("text"),
                        kwargs.get("content"),
                        kwargs.get("query"),
                        kwargs.get("input"),
                        default="",
                    )
                )
                if source_text:
                    compact = " ".join(source_text.split())
                    snippet = compact[:180]
                    result[name] = f"{name.replace('_', ' ').capitalize()}: {snippet}"
                else:
                    result[name] = (
                        f"{name.replace('_', ' ').capitalize()} produced from structured baseline analysis."
                    )
            elif "status" in name:
                result[name] = "success"
            elif "severity" in name:
                result[name] = "medium"
            else:
                result[name] = (
                    f"{name.replace('_', ' ').capitalize()} resolved for {capability_id}."
                )
        elif otype == "boolean":
            result[name] = False
        elif otype == "number":
            if "confidence" in name or "score" in name:
                result[name] = 0.64
            else:
                result[name] = 1.0
        elif otype == "array":
            if "assumption" in name:
                result[name] = [
                    {
                        "id": "asm-1",
                        "statement": "Key dependency remains available during execution.",
                        "fragility_hint": "medium",
                    }
                ]
            elif "option" in name:
                result[name] = [
                    {
                        "id": "opt-1",
                        "label": "Balanced Option",
                        "description": "Option balancing execution speed and risk.",
                    }
                ]
            elif "risk" in name:
                result[name] = [
                    {
                        "id": "risk-1",
                        "description": "Execution delay due to dependency coordination.",
                        "severity_hint": "medium",
                    }
                ]
            elif "question" in name:
                result[name] = [
                    "What additional evidence would most reduce uncertainty?"
                ]
            elif (
                "issue" in name
                or "gap" in name
                or "difference" in name
                or "conflict" in name
            ):
                result[name] = [
                    {
                        "id": "item-1",
                        "description": f"Detected {name.replace('_', ' ')} requiring follow-up analysis.",
                    }
                ]
            else:
                result[name] = [
                    {"id": "item-1", "value": f"{name} entry", "confidence": 0.64}
                ]
        elif otype == "object":
            if "plan" in name:
                result[name] = {
                    "id": _slug(capability_id, "plan"),
                    "steps": [
                        {"id": "step-1", "action": "analyze"},
                        {"id": "step-2", "action": "decide"},
                    ],
                    "status": "ready",
                }
            elif "report" in name:
                result[name] = {
                    "user_response": "Structured response ready for downstream delivery.",
                    "artifacts": [
                        {
                            "name": "summary",
                            "type": "text",
                            "content": "Actionable summary.",
                        }
                    ],
                    "limitations": [],
                }
            elif (
                "result" in name
                or "evaluation" in name
                or "validation" in name
                or "authorization" in name
            ):
                result[name] = {
                    "status": "success",
                    "confidence": 0.64,
                    "rationale": "Result assembled from deterministic baseline checks.",
                }
            elif "context" in name:
                result[name] = {
                    "summary": "Context object available for next capability stage.",
                    "key_facts": ["deterministic_baseline"],
                }
            elif "recommendation" in name:
                result[name] = {
                    "choice": "option_1",
                    "confidence": 0.64,
                    "caveats": [
                        "Validate with external evidence before final commitment."
                    ],
                }
            elif "citation" in name:
                result[name] = {
                    "id": "cit-1",
                    "title": "Deterministic Baseline Reference",
                    "url": "https://example.local/reference",
                }
            else:
                result[name] = {
                    "id": _slug(name, "obj"),
                    "summary": f"Structured object for {name.replace('_', ' ')}.",
                    "status": "available",
                }
        else:
            result[name] = None

    return result


_SPECIALS = {
    "perception_input_structure": _perception_input_structure,
    "perception_entity_extract": _perception_entity_extract,
    "perception_keyword_extract": _perception_keyword_extract,
    "reasoning_goal_interpret": _reasoning_goal_interpret,
    "decision_input_route": _decision_input_route,
    "reasoning_assumption_extract": _reasoning_assumption_extract,
    "reasoning_constraint_extract": _reasoning_constraint_extract,
    "reasoning_constraint_reconcile": _reasoning_constraint_reconcile,
    "reasoning_content_compare": _reasoning_content_compare,
    "reasoning_criteria_define": _reasoning_criteria_define,
    "reasoning_embedding_generate": _reasoning_embedding_generate,
    "reasoning_hypothesis_generate": _reasoning_hypothesis_generate,
    "reasoning_option_analyze": _reasoning_option_analyze,
    "reasoning_option_generate": _reasoning_option_generate,
    "reasoning_plan_decompose": _reasoning_plan_decompose,
    "reasoning_plan_map": _reasoning_plan_map,
    "reasoning_plan_reconcile": _reasoning_plan_reconcile,
    "reasoning_problem_decompose": _reasoning_problem_decompose,
    "evaluation_option_score": _evaluation_option_score,
    "evaluation_output_score": _evaluation_output_score,
    "evaluation_assumption_validate": _evaluation_assumption_validate,
    "evaluation_failure_analyze": _evaluation_failure_analyze,
    "evaluation_framework_detect": _evaluation_framework_detect,
    "evaluation_framework_rank": _evaluation_framework_rank,
    "evaluation_plan_validate": _evaluation_plan_validate,
    "evaluation_hypothesis_evaluate": _evaluation_hypothesis_evaluate,
    "evaluation_hypothesis_compare": _evaluation_hypothesis_compare,
    "evaluation_uncertainty_score": _evaluation_uncertainty_score,
    "decision_option_select": _decision_option_select,
    "decision_uncertainty_prioritize": _decision_uncertainty_prioritize,
    "evidence_conflict_detect": _evidence_conflict_detect,
    "evidence_gap_detect": _evidence_gap_detect,
    "evidence_source_assess": _evidence_source_assess,
    "reasoning_response_generate": _reasoning_response_generate,
    "reasoning_risk_extract": _reasoning_risk_extract,
    "reasoning_sentiment_analyze": _reasoning_sentiment_analyze,
    "reasoning_theme_cluster": _reasoning_theme_cluster,
    "reasoning_uncertainty_extract": _reasoning_uncertainty_extract,
    "memory_context_store": _memory_context_store,
    "memory_context_retrieve": _memory_context_retrieve,
    "memory_context_update": _memory_context_update,
    "memory_context_reconcile": _memory_context_reconcile,
    "memory_context_compress": _memory_context_compress,
}


def __getattr__(name: str):
    if name in _SPECIALS:
        return _SPECIALS[name]
    if name in CAPABILITY_SPECS:

        def _op(**kwargs: Any) -> dict[str, Any]:
            return _generic_capability(name, **kwargs)

        _op.__name__ = name
        return _op
    raise AttributeError(f"module 'cognitive_baseline' has no attribute '{name}'")

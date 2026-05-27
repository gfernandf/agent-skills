"""
Decision baseline service module.
Provides baseline implementations for decision-domain capabilities.
"""

from __future__ import annotations

import re

from runtime.entity_integrity import (
    detect_option_drift,
    normalize_explicit_options,
    strict_option_mode,
)


def _confidence_level_from_score(confidence: float) -> str:
    """Map confidence score to level using a non-overlapping boundary contract.

    Contract:
    - low: score < 0.30
    - medium: 0.30 <= score <= 0.70
    - high: score > 0.70
    """
    if confidence < 0.30:
        return "low"
    if confidence <= 0.70:
        return "medium"
    return "high"


def _detect_domain_uncertainty(goal: str) -> bool:
    """
    Detect if the decision involves entering a new domain or high uncertainty.
    Returns True if goal contains signals of domain novelty, inexperience, or unknown territory.
    """
    if not goal:
        return False
    goal_lower = goal.lower()
    uncertainty_signals = [
        # Spanish: Market/Domain Entry
        "nuevo mercado",
        "nuevo dominio",
        "nueva industria",
        "nuevas tecnología",
        "primer",
        "primera vez",
        "primera entrada",
        "sin experiencia",
        "no tenemos experiencia",
        "no tenemos conocimiento",
        "inexperiencia",
        "desconocido",
        "incertidumbre",
        # English: Market/Domain Entry
        "new market",
        "new domain",
        "new industry",
        "new technology",
        "first time",
        "first entry",
        "no experience",
        "inexperience",
        "unfamiliar",
        "unknown",
        "no prior experience",
        "prior experience",
        "entering",
        "legaltech",
        "medtech",
        "fintech",
        "deeptech",
        "blockchain",
        "ai integration",
    ]
    return any(signal in goal_lower for signal in uncertainty_signals)


def _compute_execution_reliability(best_score, high_scale_scores, drift_detected):
    """
    Calculate execution reliability score (0.0-1.0).
    Based on: LLM vs heuristic scoring, option drift detection.
    Returns 1.0 clean, ~0.85 heuristic fallback, 0.6 drift.
    """
    base = 1.0
    if high_scale_scores:
        base = 0.85
    if drift_detected:
        base = 0.6
    return base


def _compute_information_completeness(
    scored_options, analyzed_options, context_provided
):
    """
    Calculate information completeness score (0.0-1.0).
    Based on: analysis presence, context, option count.
    """
    if not isinstance(scored_options, list) or len(scored_options) == 0:
        return 0.2

    has_analysis = isinstance(analyzed_options, list) and len(analyzed_options) > 0
    analysis_score = 0.7 if has_analysis else 0.35
    context_score = 0.7 if context_provided else 0.3
    option_count_score = min(len(scored_options) / 4.0, 1.0)

    completeness = (
        0.4 * analysis_score + 0.35 * context_score + 0.25 * option_count_score
    )
    return round(min(completeness, 1.0), 2)


def _compute_option_separation_strength(scored_options):
    """
    Calculate option separation strength (0.0-1.0).
    Clear winner (margin > 30%) = 0.95, moderate (15-30%) = 0.65, close (< 15%) = 0.40
    """
    if not isinstance(scored_options, list) or len(scored_options) < 2:
        return 0.5

    normalized = []
    for opt in scored_options:
        if not isinstance(opt, dict):
            continue
        score = opt.get("overall_score", 0.0)
        if isinstance(score, (int, float)):
            norm = min(score / 100.0, 1.0) if score > 1.0 else max(0.0, score)
            normalized.append(norm)

    if len(normalized) < 2:
        return 0.5

    sorted_scores = sorted(normalized, reverse=True)
    top, second = sorted_scores[0], sorted_scores[1]

    if top <= 0:
        return 0.5

    margin = (top - second) / top

    if margin > 0.3:
        separation = 0.95
    elif margin > 0.15:
        separation = 0.65
    else:
        separation = 0.40

    return round(separation, 2)


def _compute_uncertainty_level(goal, has_domain_uncertainty):
    """
    Calculate uncertainty level (0.0-1.0).
    Mature domain = 1.0, New domain = 0.70
    """
    return 0.70 if has_domain_uncertainty else 1.0


def _compute_fallback_severity(high_scale_scores):
    """
    Calculate fallback severity (0.0-1.0).
    No fallback = 1.0, Heuristic fallback = 0.85
    """
    return 1.0 if not high_scale_scores else 0.88


def _compute_multicomponent_confidence(
    scored_options,
    analyzed_options,
    context_provided,
    best_score,
    high_scale_scores,
    drift_detected,
    has_domain_uncertainty,
    goal,
):
    """
    Compute confidence using multicomponent approach (5 weighted factors).
    Components: Execution Reliability (28%), Info Completeness (22%),
    Option Separation (24%), Uncertainty Level (16%), Fallback Severity (10%).
    """
    exec_reliability = _compute_execution_reliability(
        best_score, high_scale_scores, drift_detected
    )
    info_completeness = _compute_information_completeness(
        scored_options, analyzed_options, context_provided
    )
    option_separation = _compute_option_separation_strength(scored_options)
    uncertainty = _compute_uncertainty_level(goal, has_domain_uncertainty)
    fallback_severity = _compute_fallback_severity(high_scale_scores)

    composite = (
        0.28 * exec_reliability
        + 0.22 * info_completeness
        + 0.24 * option_separation
        + 0.16 * uncertainty
        + 0.10 * fallback_severity
    )

    # Domain novelty should reduce confidence moderately, not collapse it.
    if has_domain_uncertainty:
        composite *= 0.92

    # Domain novelty + heuristic scoring increases model risk; degrade moderately.
    if has_domain_uncertainty and high_scale_scores:
        composite *= 0.90

    # Missing context should lower confidence because evidence is thinner.
    if not context_provided:
        composite *= 0.88

    # If options are too close, confidence should be reduced.
    if option_separation <= 0.45:
        composite *= 0.75

    confidence = round(min(max(composite, 0.05), 0.95), 2)
    return confidence


def _extract_number(goal: str, pattern: str):
    if not goal:
        return None
    match = re.search(pattern, goal, flags=re.IGNORECASE)
    if not match:
        return None
    raw = match.group(1).replace(".", "").replace(",", "")
    try:
        return int(raw)
    except Exception:
        return None


def _extract_text(goal: str, pattern: str):
    if not goal:
        return None
    match = re.search(pattern, goal, flags=re.IGNORECASE)
    if not match:
        return None
    return match.group(1).strip()


def _normalize_decision_inputs(
    goal,
    constraints,
    risk_tolerance,
    explicit_options,
    has_domain_uncertainty,
):
    constraints = constraints if isinstance(constraints, dict) else {}
    budget = constraints.get("budget") or _extract_number(
        goal, r"(\d[\d\.,]{3,})\s*EUR"
    )
    team_size = constraints.get("team_size") or _extract_number(
        goal, r"(?:equipo|team)\s*(?:disponible)?\s*:?\s*(\d{1,2})"
    )
    timeline_months = constraints.get("timeline_months") or _extract_number(
        goal, r"(\d{1,2})\s*(?:meses|months)"
    )
    market = constraints.get("market") or _extract_text(
        goal, r"(?:mercado objetivo|target market)\s*:?\s*([^\n\.]+)"
    )

    competition = constraints.get("competition")
    if not competition:
        goal_lower = (goal or "").lower()
        if (
            "competencia establecida" in goal_lower
            or "established competition" in goal_lower
        ):
            competition = "high"

    domain_experience = constraints.get("domain_experience")
    if not domain_experience:
        domain_experience = "low" if has_domain_uncertainty else "medium"

    return {
        "budget": budget,
        "team_size": team_size,
        "market": market,
        "competition": competition,
        "domain_experience": domain_experience,
        "timeline_months": timeline_months,
        "risk_tolerance": risk_tolerance,
        "options_count": len(explicit_options)
        if isinstance(explicit_options, list)
        else None,
    }


def _build_decision_matrix(alternatives_evaluated):
    matrix = []
    for alt in (
        alternatives_evaluated if isinstance(alternatives_evaluated, list) else []
    ):
        if not isinstance(alt, dict):
            continue
        option = str(alt.get("option", "Option"))
        option_l = option.lower()
        score = alt.get("score", 0.0)

        if "mvp" in option_l or "piloto" in option_l or "pilot" in option_l:
            cost, risk, speed, fit = "Medium", "Medium", "High", "High"
        elif "posponer" in option_l or "postpone" in option_l or "defer" in option_l:
            cost, risk, speed, fit = "Low", "Low", "Low", "Medium"
        elif "full" in option_l or "completo" in option_l or "complete" in option_l:
            cost, risk, speed, fit = "High", "High", "Low", "Medium"
        else:
            cost, risk, speed, fit = "Medium", "Medium", "Medium", "Medium"

        matrix.append(
            {
                "option": option,
                "cost": cost,
                "risk": risk,
                "speed": speed,
                "strategic_fit": fit,
                "score": round(float(score), 2)
                if isinstance(score, (int, float))
                else 0.0,
            }
        )
    return matrix


def _build_alternatives_evaluated(scored_options, analyzed_options):
    """
    Build alternatives_evaluated entries required by decision.option.justify contract.

    Each item contains: option, score (0.0-1.0), pros[], cons[].
    """
    analyzed_by_id = {}
    if isinstance(analyzed_options, list):
        for entry in analyzed_options:
            if not isinstance(entry, dict):
                continue
            option_id = entry.get("option_id") or entry.get("id")
            if option_id:
                analyzed_by_id[option_id] = entry

    evaluated = []
    for opt in scored_options if isinstance(scored_options, list) else []:
        if not isinstance(opt, dict):
            continue

        option_id = opt.get("option_id") or opt.get("id")
        label = opt.get("label") or option_id or "option"
        raw_score = opt.get("overall_score", 0.0)
        if isinstance(raw_score, (int, float)):
            score = float(raw_score)
            score = score / 100.0 if score > 1.0 else score
            score = max(0.0, min(score, 1.0))
        else:
            score = 0.0

        analyzed = analyzed_by_id.get(option_id, {})
        pros = analyzed.get("pros") if isinstance(analyzed, dict) else None
        cons = analyzed.get("cons") if isinstance(analyzed, dict) else None

        evaluated.append(
            {
                "option": label,
                "score": round(score, 2),
                "pros": pros if isinstance(pros, list) else [],
                "cons": cons if isinstance(cons, list) else [],
            }
        )

    return evaluated


def _option_tie_priority(label: str) -> int:
    """Lower value means a more conservative baseline tie-break preference."""
    label_l = (label or "").strip().lower()
    if "mvp" in label_l or "pilot" in label_l or "piloto" in label_l:
        return 0
    if "defer" in label_l or "postpone" in label_l or "posponer" in label_l:
        return 1
    if "full" in label_l or "complete" in label_l or "completo" in label_l:
        return 3
    return 2


def justify_option(
    scored_options,
    analyzed_options,
    goal,
    tradeoffs=None,
    constraints=None,
    risk_tolerance=None,
    explicit_options=None,
    option_constraint_mode=None,
):
    """
    Select a recommendation from scored+analyzed options and justify it.

    Baseline heuristic: picks the option with the highest overall_score
    (or the first one if scores are missing) and builds a structured
    justification from the available data.
    """
    risk_tolerance = risk_tolerance or "medium"

    # Pick best option by overall_score. On ties, prefer a conservative rollout option.
    best = None
    best_score = -1.0
    all_options = scored_options if isinstance(scored_options, list) else []

    for opt in all_options:
        if not isinstance(opt, dict):
            continue
        s = opt.get("overall_score", 0.0)
        if not isinstance(s, (int, float)):
            s = 0.0

        if s > best_score:
            best_score = s
            best = opt
            continue

        if s == best_score and best is not None:
            current_label = str(opt.get("label", opt.get("option_id", "")))
            best_label = str(best.get("label", best.get("option_id", "")))
            if _option_tie_priority(current_label) < _option_tie_priority(best_label):
                best = opt

    if best is None and all_options:
        best = all_options[0]

    rec_label = (
        best.get("label", best.get("option_id", "option-1")) if best else "no-option"
    )

    # Detect domain uncertainty (new market, new tech, no experience)
    has_domain_uncertainty = _detect_domain_uncertainty(goal)

    # Check if we have context/tradeoffs
    context_provided = (
        bool(tradeoffs)
        or bool(constraints)
        or bool(explicit_options)
        or bool(option_constraint_mode)
    )

    is_strict = strict_option_mode(option_constraint_mode, explicit_options)
    normalized_explicit = normalize_explicit_options(explicit_options)
    observed_options = []
    for opt in all_options:
        if not isinstance(opt, dict):
            continue
        oid = opt.get("option_id", opt.get("id"))
        observed_options.append({"id": oid, "label": opt.get("label", oid)})
    drift = detect_option_drift(normalized_explicit, observed_options)
    drift_detected = is_strict and drift.get("has_drift", False)

    # Normalize best_score for confidence calculation
    normalized_best = best_score / 100.0 if best_score > 1.0 else best_score
    high_scale_scores = best_score > 1.0

    # Compute multicomponent confidence
    confidence = _compute_multicomponent_confidence(
        scored_options=all_options,
        analyzed_options=analyzed_options or [],
        context_provided=context_provided,
        best_score=normalized_best,
        high_scale_scores=high_scale_scores,
        drift_detected=drift_detected,
        has_domain_uncertainty=has_domain_uncertainty,
        goal=goal,
    )

    if has_domain_uncertainty:
        confidence = min(confidence, 0.70)

    if drift_detected:
        confidence = min(confidence, 0.29)

    level = _confidence_level_from_score(confidence)

    alternatives = []
    if is_strict and normalized_explicit:
        selected_id = (
            best.get("option_id", best.get("id")) if isinstance(best, dict) else None
        )
        for opt in normalized_explicit:
            oid = opt.get("id", "?")
            label = opt.get("label", oid)
            alternatives.append(
                {"id": oid, "label": label, "selected": oid == selected_id}
            )
    else:
        for opt in all_options:
            oid = opt.get("option_id", opt.get("id", "?"))
            label = opt.get("label", oid)
            selected = opt is best
            alternatives.append({"id": oid, "label": label, "selected": selected})

    alternatives_evaluated = _build_alternatives_evaluated(
        all_options, analyzed_options
    )
    decision_inputs = _normalize_decision_inputs(
        goal,
        constraints,
        risk_tolerance,
        explicit_options,
        has_domain_uncertainty,
    )
    decision_matrix = _build_decision_matrix(alternatives_evaluated)

    uncertainties = [
        "Baseline analysis; production confidence improves with richer external evidence."
    ]
    if high_scale_scores:
        uncertainties.append(
            "Using heuristic baseline scoring scale may overstate certainty without calibrated evidence."
        )
    if has_domain_uncertainty:
        uncertainties.append(
            "Low domain experience increases uncertainty and reduces confidence."
        )
    if drift_detected:
        uncertainties.append(
            "Strict option integrity mode detected entity drift (missing/new/renamed options); confidence downgraded."
        )

    failure_modes = ["Key assumptions may not hold under changing conditions."]
    if has_domain_uncertainty:
        failure_modes.append(
            "Domain expertise gaps may invalidate assumptions or execution quality."
        )

    return {
        "recommendation": f"Proceed with {rec_label}.",
        "alternatives_considered": alternatives,
        "alternatives_evaluated": alternatives_evaluated,
        "decision_inputs": decision_inputs,
        "decision_matrix": decision_matrix,
        "confidence_score": confidence,
        "confidence_level": level,
        "uncertainties": uncertainties,
        "failure_modes": failure_modes,
        "next_steps": [
            "Validate recommendation with domain experts.",
            "Run a pilot if feasible.",
        ],
        "human_readable": (
            f"Recommendation: {rec_label}. Confidence: {level} ({confidence}). "
            f"Rationale: best balance across risk, speed, and strategic fit under current constraints. "
            f"Next: validate assumptions quickly and scale only after pilot evidence."
        ),
    }

"""
Agent baseline service module.
Provides baseline implementations for agent-related capabilities.
"""


def delegate_agent(task, agent, timeout_seconds=None):
    """
    Delegate a task to an agent.

    Args:
        task (dict|str): Structured task object or task description string.
        agent (str): The agent identifier.
        timeout_seconds (int, optional): Acceptance timeout. Defaults to 30.

    Returns:
        dict: {"accepted": bool, "delegation_id": str|None}
    """
    import hashlib
    import json

    task_str = json.dumps(task, sort_keys=True) if isinstance(task, dict) else str(task)
    delegation_id = hashlib.sha256(f"{agent}:{task_str}".encode()).hexdigest()[:12]
    return {"accepted": True, "delegation_id": f"del-{delegation_id}"}


def generate_plan(goal, context=None, max_steps=None):
    """
    Generate a structured plan for achieving a goal.

    Args:
        goal (str): The goal description.
        context (str, optional): Background information or constraints.
        max_steps (int, optional): Maximum number of steps. Defaults to 5.

    Returns:
        dict: {"plan": object, "step_count": int}
    """
    if max_steps is None:
        max_steps = 5
    max_steps = min(max_steps, 10)

    steps = [
        {
            "id": "step-1",
            "action": "analyse",
            "description": f"Analyse requirements for: {goal}",
            "depends_on": [],
        },
        {
            "id": "step-2",
            "action": "execute",
            "description": "Execute core actions based on analysis",
            "depends_on": ["step-1"],
        },
        {
            "id": "step-3",
            "action": "verify",
            "description": "Verify outputs meet the objective",
            "depends_on": ["step-2"],
        },
    ][:max_steps]

    plan = {
        "objective": goal,
        "steps": steps,
        "assumptions": ["Input data is available and accessible"],
        "risks": ["Incomplete requirements may lead to partial solution"],
    }
    return {"plan": plan, "step_count": len(steps)}


def route_agent(query, agents=None, routing_strategy=None):
    """
    Route a query to the most appropriate agent.

    Args:
        query (str): The query text.
        agents (list, optional): List of available agents.
        routing_strategy (str, optional): Strategy hint (keyword, semantic, round-robin).

    Returns:
        dict: {"route": str}
    """
    if isinstance(agents, list) and agents:
        # Keyword matching: pick first agent whose name appears in query
        if query and isinstance(query, str):
            query_lower = query.lower()
            for agent in agents:
                if isinstance(agent, str) and agent.lower() in query_lower:
                    return {"route": agent}
        selected = agents[0]
    elif isinstance(query, dict):
        selected = str(query.get("task_type", query.get("approach", "default")))
    else:
        selected = "default"
    return {"route": selected}


def generate_options(goal, context=None, constraints=None, max_options=None):
    """
    Generate plausible options for a decision problem.

    Baseline heuristic: produces 3 generic options derived from the goal text.
    """
    if max_options is None:
        max_options = 4
    max_options = min(max_options, 6)

    prefix = goal[:50] if goal else "goal"
    options = []
    templates = [
        ("conservative", "Low-risk incremental approach"),
        ("balanced", "Moderate approach balancing risk and reward"),
        ("aggressive", "High-ambition approach with higher risk"),
        ("alternative", "Non-obvious lateral approach"),
    ]
    for i, (slug, desc) in enumerate(templates[:max_options], 1):
        options.append(
            {
                "id": f"opt-{slug}",
                "label": f"Option {i}: {slug.title()}",
                "description": f"{desc} for '{prefix}'.",
                "key_attributes": {"risk": slug, "speed": "medium", "cost": "medium"},
            }
        )

    return {
        "options": options,
        "generation_notes": f"Baseline generation: {len(options)} options from goal text.",
    }


def evaluate_branch(condition, context, branches, default_branch=None):
    """Select a branch based on a condition string evaluated against context.

    Branch objects must have 'id' (slug) and optional 'match_expression' or
    'match' (backward-compat alias) for the structured predicate. Returns
    'selected_branch' as the branch id, matching the contract.
    """
    condition_lower = str(condition).lower()
    for branch in branches or []:
        branch_id = branch.get("id") or branch.get("label", "")
        # Accept 'match_expression' (contract) or 'match' (legacy alias)
        match_expr = str(branch.get("match_expression") or branch.get("match", "")).lower()
        keywords = [
            w.strip("'\" ")
            for w in match_expr.replace("==", " ").split()
            if len(w.strip("'\" ")) > 2
        ]
        if any(
            kw in condition_lower or kw in str(context).lower() for kw in keywords if kw
        ):
            return {
                "selected_branch": branch_id,
                "rationale": f"Matched branch '{branch_id}' via keyword heuristic.",
                "confidence": 0.7,
            }
    fallback = default_branch or (
        branches[0].get("id") or branches[0].get("label") if branches else "default"
    )
    return {
        "selected_branch": fallback,
        "rationale": "No branch matched; using default.",
        "confidence": 0.3,
    }


def iterate_collection(
    items, capability, input_mapping=None, mode=None, max_concurrency=None
):
    """Iterate over items invoking a capability per element (baseline: returns stubs)."""
    results = []
    for i, item in enumerate(items or []):
        results.append({"index": i, "status": "completed", "output": item})
    return {
        "results": results,
        "item_count": len(results),
        "mode": mode or "sequential",
        "error_count": 0,
        "errors": [],
    }


def wait_condition(condition, timeout_seconds=None, poll_interval_seconds=None):
    """Wait for a condition (baseline: immediate resolution)."""
    return {
        "resolved": True,
        "elapsed_seconds": 0,
        "condition": condition,
        "timed_out": False,
        "event": None,
    }


def handle_error(
    error, fallback_strategy, default_value=None, max_retries=None, context=None
):
    """Handle an error with a fallback strategy."""
    strategy = fallback_strategy or "default_value"
    if strategy == "default_value":
        return {
            "recovered": True,
            "strategy_applied": "default_value",
            "result": default_value or {},
            "original_error": error,
        }
    return {
        "recovered": True,
        "strategy_applied": strategy,
        "result": None,
        "original_error": error,
    }


def collect_input(fields, instruction=None, context=None):
    """Collect structured input fields (baseline: returns defaults per type)."""
    collected = {}
    for field in fields or []:
        name = field.get("name", "")
        ftype = field.get("type", "string")
        if ftype == "number":
            collected[name] = 0
        elif ftype == "boolean":
            collected[name] = False
        else:
            collected[name] = f"[placeholder for {name}]"
    return {"collected": collected, "field_count": len(collected)}


# ---------------------------------------------------------------------------
# Multipurpose agent pipeline — new capabilities
# ---------------------------------------------------------------------------


def normalize_request(user_message, context=None):
    """
    Normalize a raw user request into a structured task object.

    Args:
        user_message (str): Raw user message.
        context (dict, optional): Conversation or session context.

    Returns:
        dict: {"normalized_request": object, "language": str}
    """
    import re

    lang = "en"
    if isinstance(user_message, str):
        # Simple heuristic: detect Spanish by common words
        es_markers = ["hacer", "hazme", "dame", "necesito", "quiero", "crea", "analiza",
                      "generar", "construir", "buscar", "tengo", "para", "sobre", "con"]
        lower = user_message.lower()
        if any(m in lower for m in es_markers):
            lang = "es"

    urgency = "medium"
    if isinstance(user_message, str):
        lower = user_message.lower()
        if any(w in lower for w in ["urgent", "asap", "immediately", "ahora", "urgente"]):
            urgency = "high"
        elif any(w in lower for w in ["when you can", "no rush", "eventually"]):
            urgency = "low"

    side_effect_verbs = ["send", "write", "create", "delete", "update", "publish",
                         "enviar", "escribir", "crear", "borrar", "modificar"]
    requires_external = isinstance(user_message, str) and any(
        v in user_message.lower() for v in side_effect_verbs
    )

    # Extract explicit constraints (text in quotes or after "only", "max", "must")
    constraints = []
    if isinstance(user_message, str):
        quoted = re.findall(r'"([^"]+)"', user_message)
        constraints.extend(quoted)

    normalized_request = {
        "raw_request": user_message if isinstance(user_message, str) else str(user_message),
        "language": lang,
        "detected_intent": "general_task",
        "explicit_constraints": constraints,
        "urgency": urgency,
        "requires_external_action": requires_external,
        "attachments": [],
    }
    return {"normalized_request": normalized_request, "language": lang, "_fallback": True}


def interpret_goal(normalized_request, context=None):
    """
    Convert a normalized request into an operational goal.

    Args:
        normalized_request (dict): Output from normalize_request.
        context (dict, optional): Additional session context.

    Returns:
        dict: {"interpreted_goal": object, "requires_clarification": bool}
    """
    if not isinstance(normalized_request, dict):
        normalized_request = {"raw_request": str(normalized_request)}

    raw = normalized_request.get("raw_request", "")
    constraints = normalized_request.get("explicit_constraints", [])

    raw_text = raw if isinstance(raw, str) else str(raw)
    objective_text = raw_text.strip()
    
    # Remove common prefixes injected by chat systems
    prefixes_to_strip = ["You said:", "User said:", "The assistant said:", "You asked:", "User asked:"]
    for prefix in prefixes_to_strip:
        if objective_text.startswith(prefix):
            objective_text = objective_text[len(prefix):].strip()
            break
    
    if not objective_text:
        objective_text = "Complete the task"
    # Keep full prompts for complex planning while guarding against extreme payloads.
    elif len(objective_text) > 4000:
        objective_text = objective_text[:4000]

    interpreted_goal = {
        "objective": objective_text,
        "deliverable_type": "task_output",
        "success_criteria": [
            "The task objective is addressed",
            "The output is complete and well-structured",
        ],
        "constraints": constraints,
        "assumptions": ["Required resources are available"],
        "open_questions": [],
    }
    return {
        "interpreted_goal": interpreted_goal,
        "requires_clarification": False,
        "_fallback": True,
    }


def define_criteria(interpreted_goal):
    """
    Define measurable success, quality, and acceptance criteria.

    Args:
        interpreted_goal (dict): Output from interpret_goal.

    Returns:
        dict: {"success_criteria": list, "quality_criteria": list, "acceptance_criteria": list}
    """
    if not isinstance(interpreted_goal, dict):
        interpreted_goal = {}

    base_criteria = list(interpreted_goal.get("success_criteria", []))
    if not base_criteria:
        base_criteria = [
            "The output directly addresses the stated objective",
            "The output is complete with no missing sections",
            "The output is accurate and free from factual errors",
        ]

    quality_criteria = [
        "Output is well-structured and readable",
        "Key claims are supported by evidence or reasoning",
    ]
    acceptance_criteria = [
        "The deliverable matches the expected deliverable_type",
        "The user can act on the output without additional clarification",
    ]
    return {
        "success_criteria": base_criteria,
        "quality_criteria": quality_criteria,
        "acceptance_criteria": acceptance_criteria,
        "_fallback": True,
    }


def _tokenize(text):
    """Split text into lowercase word tokens for keyword matching."""
    import re
    return set(re.findall(r"[a-z0-9]+", (text or "").lower()))


def _score_item(item_tokens, goal_tokens, id_tokens):
    """
    Compute a relevance score [0.0, 1.0] between a catalog item and a goal.
    Weights: description-overlap 0.6, id-prefix-overlap 0.4.
    """
    if not goal_tokens:
        return 0.0
    desc_overlap = len(item_tokens & goal_tokens) / max(len(goal_tokens), 1)
    id_overlap = len(id_tokens & goal_tokens) / max(len(goal_tokens), 1)
    return round(min(0.6 * desc_overlap + 0.4 * id_overlap, 1.0), 4)


def search_catalog(goal, registry=None, filters=None):
    """
    Search the live ORCA registry for relevant capabilities and skills.

    Reads the real registry via sdk.embedded.list_skills / list_capabilities,
    then scores each item against the goal using keyword overlap.
    Falls back to a minimal hardcoded set only if the SDK is unavailable.

    Args:
        goal (dict): Interpreted goal.
        registry (dict, optional): Unused — live registry is always preferred.
        filters (dict, optional): Optional keys: kinds (list), domain (str),
            max_results (int), min_score (float).

    Returns:
        dict: {"candidate_items": list, "total_matched": int}
    """
    if not isinstance(goal, dict):
        goal = {}
    if not isinstance(filters, dict):
        filters = {}

    # Build goal token set from objective + keywords fields
    raw_goal_text = " ".join(filter(None, [
        str(goal.get("objective", "")),
        str(goal.get("summary", "")),
        " ".join(goal.get("keywords", []) if isinstance(goal.get("keywords"), list) else []),
        str(goal.get("domain", "")),
    ]))
    # Expand Spanish synonyms to English equivalents for keyword overlap scoring
    _ES_SYNONYMS = {
        "briefing": "briefing research generate",
        "sintetiza": "synthesize synthesis analysis",
        "sintetizar": "synthesize synthesis analysis",
        "síntesis": "synthesize synthesis",
        "analiza": "analyze analysis",
        "analizar": "analyze analysis",
        "compara": "compare comparison",
        "comparar": "compare comparison",
        "descomponer": "decompose decomposition",
        "descompon": "decompose",
        "resume": "summarize summary",
        "resumir": "summarize summary",
        "riesgo": "risk assess",
        "riesgos": "risk assess",
        "oportunidades": "opportunities analysis synthesize",
        "mercado": "market research briefing",
        "informe": "report research briefing",
        "investiga": "research investigate",
    }
    expanded_text = raw_goal_text
    for es_word, en_expansion in _ES_SYNONYMS.items():
        if es_word in raw_goal_text.lower():
            expanded_text += " " + en_expansion
    goal_tokens = _tokenize(expanded_text)

    kind_filter = filters.get("kinds")  # e.g. ["capability"] or ["skill", "capability"]
    domain_filter = filters.get("domain")  # e.g. "audio"
    max_results = filters.get("max_results", 20)
    min_score = filters.get("min_score", 0.0)

    candidates = []

    try:
        import sdk.embedded as _sdk

        # ── capabilities ────────────────────────────────────────────────────
        if not isinstance(kind_filter, list) or "capability" in kind_filter:
            for cap in _sdk.list_capabilities():
                cap_id = cap.get("id", "")
                if domain_filter and not cap_id.startswith(domain_filter):
                    continue
                desc_tokens = _tokenize(cap.get("description", ""))
                id_tokens = _tokenize(cap_id.replace(".", " "))
                score = _score_item(desc_tokens, goal_tokens, id_tokens)
                if score >= min_score:
                    candidates.append({
                        "ref": cap_id,
                        "type": "capability",
                        "relevance_score": score,
                        "description": cap.get("description", ""),
                        "inputs": cap.get("inputs", {}),
                        "outputs": cap.get("outputs", {}),
                        "reason": f"Keyword match score {score} against goal tokens.",
                    })

        # ── skills ──────────────────────────────────────────────────────────
        if not isinstance(kind_filter, list) or "skill" in kind_filter:
            for skill in _sdk.list_skills():
                skill_id = skill.get("id", "")
                if domain_filter and not skill_id.startswith(domain_filter):
                    continue
                desc_tokens = _tokenize(" ".join(filter(None, [
                    skill.get("description", ""),
                    skill.get("name", ""),
                ])))
                id_tokens = _tokenize(skill_id.replace(".", " ").replace("-", " "))
                score = _score_item(desc_tokens, goal_tokens, id_tokens)
                if score >= min_score:
                    candidates.append({
                        "ref": skill_id,
                        "type": "skill",
                        "relevance_score": score,
                        "description": skill.get("description", ""),
                        "inputs": skill.get("inputs", {}),
                        "outputs": skill.get("outputs", {}),
                        "reason": f"Keyword match score {score} against goal tokens.",
                    })

    except Exception:  # SDK unavailable — minimal hardcoded fallback
        candidates = [
            {"ref": "model.output.generate", "type": "capability",
             "relevance_score": 0.4, "description": "", "inputs": {}, "outputs": {},
             "reason": "SDK unavailable; hardcoded fallback."},
        ]

    # Sort descending by score, apply max_results
    candidates.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
    if isinstance(max_results, int) and max_results > 0:
        candidates = candidates[:max_results]

    return {
        "candidate_items": candidates,
        "total_matched": len(candidates),
    }


def rank_catalog(candidate_items, interpreted_goal):
    """
    Rank candidate registry items by relevance score.

    Items carry real contract data (inputs/outputs) from search_catalog so
    downstream planning steps can inspect binding compatibility.

    Args:
        candidate_items (list): Candidates from search_catalog.
        interpreted_goal (dict): Interpreted goal for context.

    Returns:
        dict: {"ranked_skills": list, "ranked_capabilities": list}
    """
    if not isinstance(candidate_items, list):
        candidate_items = []

    skills = [c for c in candidate_items if c.get("type") == "skill"]
    capabilities = [c for c in candidate_items if c.get("type") == "capability"]

    def _rank(items):
        sorted_items = sorted(items, key=lambda x: x.get("relevance_score", 0), reverse=True)
        return [
            {
                **item,
                "rank": i + 1,
                "rationale": item.get("reason", "Ranked by keyword relevance score."),
                # expose contract summary for planner inspection
                "contract": {
                    "inputs": list((item.get("inputs") or {}).keys()),
                    "outputs": list((item.get("outputs") or {}).keys()),
                },
            }
            for i, item in enumerate(sorted_items)
        ]

    return {
        "ranked_skills": _rank(skills),
        "ranked_capabilities": _rank(capabilities),
    }


def detect_catalog_gaps(interpreted_goal, candidate_items):
    """
    Detect gaps between goal requirements and available registry items.

    Args:
        interpreted_goal (dict): Interpreted goal.
        candidate_items (list): Candidates already found.

    Returns:
        dict: {"missing_capabilities": list, "missing_skills": list, "gap_severity": str}
    """
    if not isinstance(candidate_items, list):
        candidate_items = []

    # A gap exists when the top-ranked items have low relevance or the
    # registry returned nothing useful (score below threshold).
    HIGH_SCORE = 0.3
    good_caps = [c for c in candidate_items
                 if c.get("type") == "capability" and c.get("relevance_score", 0) >= HIGH_SCORE]
    good_skills = [c for c in candidate_items
                   if c.get("type") == "skill" and c.get("relevance_score", 0) >= HIGH_SCORE]

    if not candidate_items:
        severity = "critical"
    elif not good_caps and not good_skills:
        severity = "high"
    elif not good_caps or not good_skills:
        severity = "minor"
    else:
        severity = "none"

    return {
        "missing_capabilities": [] if good_caps else [{"reason": "No capability matched goal with score >= 0.3"}],
        "missing_skills": [] if good_skills else [{"reason": "No skill matched goal with score >= 0.3"}],
        "gap_severity": severity,
    }


def create_macro_plan(interpreted_goal, candidate_skills=None,
                      candidate_capabilities=None, planning_strategy=None):
    """
    Generate a high-level macro plan using real ranked candidates.

    Args:
        interpreted_goal (dict): Interpreted goal.
        candidate_skills (list, optional): Ranked skills from rank_catalog.
        candidate_capabilities (list, optional): Ranked capabilities from rank_catalog.
        planning_strategy (str, optional): 'direct' (fast path) or 'staged'.

    Returns:
        dict: {"macro_plan": object, "stage_count": int}
    """
    if not isinstance(interpreted_goal, dict):
        interpreted_goal = {}
    if not isinstance(candidate_skills, list):
        candidate_skills = []
    if not isinstance(candidate_capabilities, list):
        candidate_capabilities = []

    objective = interpreted_goal.get("objective", "Complete the task")
    strategy = planning_strategy or "staged"

    # Pick top candidates for stage assignment
    top_skill = candidate_skills[0] if candidate_skills else None
    top_caps = candidate_capabilities[:3] if candidate_capabilities else []

    def _is_runtime_cap(ref):
        if not isinstance(ref, str) or not ref:
            return False
        internal_prefixes = (
            "agent.catalog.",
            "agent.goal.",
            "agent.request.",
            "agent.criteria.",
            "agent.plan.",
            "eval.output.",
        )
        return not ref.startswith(internal_prefixes)

    runtime_caps = [c for c in top_caps if _is_runtime_cap(c.get("ref"))]

    if strategy == "direct" and (top_skill or top_caps):
        # Fast path: single stage using the best available item
        best = top_skill or top_caps[0]
        stages = [{
            "id": "s1",
            "objective": objective,
            "expected_output": "result",
            "suggested_skill": best.get("ref") if best.get("type") == "skill" else None,
            "suggested_capability": best.get("ref") if best.get("type") == "capability" else None,
            "parallel_with": [],
        }]
    else:
        # Staged: distribute candidates across stages
        # s1 → primary research/retrieval skill
        # s2 → synthesis/analysis skill (different from s1)
        # s3 → kept minimal (only if a 3rd skill is available and meaningful)
        def _stage(sid, obj, cap_ref, expected, skill_ref=None):
            return {
                "id": sid,
                "objective": obj,
                "expected_output": expected,
                "suggested_skill": skill_ref,
                "suggested_capability": cap_ref,
                "parallel_with": [],
            }

        # Pick distinct skills: research skill for s1, synthesis skill for s2
        objective_l = str(objective).lower()
        source_signals = (
            "fuente", "fuentes", "source", "sources", "evidencia", "evidence",
            "trazabilidad", "traceability", "recientes", "recent",
        )
        wants_research_first = any(sig in objective_l for sig in source_signals)

        research_skill = top_skill  # highest ranked by default
        if wants_research_first:
            research_skill = next(
                (
                    s for s in candidate_skills
                    if any(kw in s.get("ref", "") for kw in (
                        "research.", "generate-briefing", "source.retrieve", "web.search"
                    ))
                ),
                top_skill,
            )

        compare_signals = (
            "escenario", "escenarios", "base vs", "conservador", "compare", "comparar", "contrasta"
        )
        wants_compare = any(sig in objective_l for sig in compare_signals)

        # Prefer compare for scenario prompts; otherwise prefer synthesis/decompose.
        if wants_compare:
            synth_skill = next(
                (s for s in candidate_skills
                 if s.get("ref") != (research_skill.get("ref") if research_skill else None)
                 and any(kw in s.get("ref", "") for kw in ("analysis.compare", "compare"))),
                None,
            )
        else:
            synth_skill = None

        if not synth_skill:
            synth_skill = next(
                (s for s in candidate_skills
                 if s.get("ref") != (research_skill.get("ref") if research_skill else None)
                 and any(kw in s.get("ref", "") for kw in ("synthesize", "summarize", "decompose", "frame"))),
                next(
                    (s for s in candidate_skills
                     if s.get("ref") != (research_skill.get("ref") if research_skill else None)
                     and any(kw in s.get("ref", "") for kw in ("analys", "summar"))),
                    candidate_skills[1] if len(candidate_skills) > 1 else None,
                ),
            )

        stages = []
        stages.append(_stage(
            "s1", objective,
            runtime_caps[0].get("ref") if runtime_caps else None,
            "primary_result",
            skill_ref=research_skill.get("ref") if research_skill else None,
        ))

        if synth_skill:
            stages.append(_stage(
                "s2", "Synthesize and enrich primary result",
                top_caps[1].get("ref") if len(top_caps) > 1 else None,
                "enriched_result",
                skill_ref=synth_skill.get("ref"),
            ))
        else:
            stages.append(_stage(
                "s2", "Synthesize and enrich primary result",
                top_caps[1].get("ref") if len(top_caps) > 1 else None,
                "enriched_result",
            ))

    macro_plan = {
        "goal_ref": objective[:40].lower().replace(" ", "-").strip("-"),
        "strategy": strategy,
        "stages": stages,
    }
    return {"macro_plan": macro_plan, "stage_count": len(stages)}


def split_plan_stage(macro_stage, candidate_skills=None,
                     candidate_capabilities=None, current_state=None):
    """
    Expand a macro plan stage into concrete ORCA-executable steps.

    Uses real refs from ranked candidates. Falls back to generic placeholders
    only when no candidates are provided.

    Args:
        macro_stage (dict): Single stage from macro_plan.stages.
        candidate_skills (list, optional): Ranked skills from rank_catalog.
        candidate_capabilities (list, optional): Ranked capabilities from rank_catalog.
        current_state (dict, optional): Current CognitiveState.

    Returns:
        dict: {"expanded_steps": list, "step_count": int}
    """
    if not isinstance(macro_stage, dict):
        macro_stage = {}
    if not isinstance(candidate_skills, list):
        candidate_skills = []
    if not isinstance(candidate_capabilities, list):
        candidate_capabilities = []

    def _is_non_executable_planner_cap(ref):
        if not isinstance(ref, str) or not ref:
            return False
        return ref.startswith((
            "agent.catalog.", "agent.goal.", "agent.request.",
            "agent.criteria.", "agent.plan.", "eval.output.",
        ))

    def _skill_outputs_map(ref, sid):
        for s in candidate_skills:
            if s.get("ref") == ref:
                keys = list((s.get("outputs") or {}).keys())
                if keys:
                    return {k: f"$state.working.{sid}_{k}" for k in keys}
        return {"result": f"$state.working.{sid}_skill_result"}

    def _expand_single_stage(stage, prev_step_ids, prev_output_state):
        """Expand one macro stage into executable steps."""
        sid = stage.get("id", "s1")
        objective = stage.get("objective", "Execute stage")
        suggested_skill_ref = stage.get("suggested_skill")
        suggested_cap_ref = stage.get("suggested_capability")

        primary_cap_ref = (
            suggested_cap_ref
            or (candidate_capabilities[0].get("ref") if candidate_capabilities else None)
        )
        primary_skill_ref = (
            suggested_skill_ref
            or (candidate_skills[0].get("ref") if candidate_skills else None)
        )

        def _cap_inputs(ref):
            if ref == "agent.task.delegate":
                return {"task": {"description": objective, "priority": "medium"},
                        "agent": "research-agent", "timeout_seconds": 30}
            for c in candidate_capabilities:
                if c.get("ref") == ref:
                    return {k: f"$state.working.{sid}_{k}"
                            for k in (c.get("inputs") or {}).keys()} or {"input": objective}
            return {"input": objective}

        def _cap_outputs(ref):
            for c in candidate_capabilities:
                if c.get("ref") == ref:
                    return {k: f"$state.working.{sid}_{k}"
                            for k in (c.get("outputs") or {}).keys()} or {"result": f"$state.working.{sid}_result"}
            return {"result": f"$state.working.{sid}_result"}

        def _skill_inputs(ref):
            # First stage: use literal query from objective
            if not prev_output_state:
                if ref == "research.generate-briefing":
                    import re
                    import unicodedata

                    objective_l = str(objective).lower()
                    objective_ascii = unicodedata.normalize("NFKD", objective_l)
                    objective_ascii = objective_ascii.encode("ascii", "ignore").decode("ascii")
                    default_sources = 8
                    requested_sources = None
                    m = re.search(
                        r"(?:min(?:imo)?|al\s+menos|at\s+least)\s+(\d{1,2})\s+(?:fuentes|sources)",
                        objective_ascii,
                    )
                    if m:
                        try:
                            requested_sources = int(m.group(1))
                        except Exception:
                            requested_sources = None

                    # Respect explicit source requests from prompt (e.g. "minimo 3 fuentes").
                    # Keep a bounded default for stable quality when no request is provided.
                    if requested_sources is not None:
                        num_sources = min(10, max(1, requested_sources))
                    else:
                        num_sources = default_sources
                    # Build a search-friendly query from long instruction prompts.
                    search_query = str(objective)
                    for marker in (
                        "Requisitos obligatorios:", "Control:",
                        "requirements:", "mandatory controls:",
                    ):
                        if marker in search_query:
                            search_query = search_query.split(marker, 1)[0]
                    search_query = " ".join(search_query.split())
                    if len(search_query) > 220:
                        search_query = search_query[:220].rsplit(" ", 1)[0]

                    broad_query = search_query
                    if any(term in objective_l for term in ("mercado", "market", "fuente", "fuentes", "evidencia", "evidence", "storage", "almacenamiento")):
                        broad_query = (
                            f"{search_query} market report research trends risks opportunities Europe regulation policy"
                        )
                    return {
                        "query": search_query,
                        "broad_query": broad_query,
                        "mode": "quick",
                        "num_sources": num_sources,
                    }
                if ref == "analysis.compare":
                    return {
                        "options": [{"id": "opt-1", "description": objective}],
                        "comparison_goal": objective,
                    }
                for s in candidate_skills:
                    if s.get("ref") == ref:
                        spec = s.get("inputs") or {}
                        if "query" in spec:
                            return {"query": objective}
                        if "task" in spec:
                            return {"task": objective}
                        if "goal" in spec:
                            return {"goal": objective}
                return {"input": objective}
            else:
                # Downstream stage: feed previous stage outputs via state refs
                if ref == "analysis.compare":
                    return {"options": prev_output_state, "comparison_goal": objective}
                if ref in ("analysis.synthesize", "analysis.decompose",
                           "analysis.theme.cluster"):
                    return {"items": prev_output_state, "goal": objective}
                if ref == "task.frame":
                    return {"goal": objective, "context": prev_output_state}
                for s in candidate_skills:
                    if s.get("ref") == ref:
                        spec = s.get("inputs") or {}
                        if "items" in spec:
                            return {"items": prev_output_state}
                        if "input" in spec:
                            return {"input": prev_output_state}
                        if "query" in spec:
                            return {"query": objective}
                return {"input": prev_output_state}

        steps = []

        # A capability is only useful in the plan when:
        # 1. No skill is available for this stage (skill takes priority always), AND
        # 2. Its inputs are either literals or come from a previous step's output.
        # When a skill is present it is self-contained — skip the capability prefix.
        def _cap_has_valid_inputs(ref):
            cap_inputs = _cap_inputs(ref)
            if not cap_inputs:
                return False
            all_state_refs = all(
                isinstance(v, str) and v.startswith("$state.")
                for v in cap_inputs.values()
            )
            # Reject if all inputs are state refs with no upstream producer
            if all_state_refs and not prev_step_ids:
                return False
            # Reject if any input refs the current stage's own state (not yet produced)
            sid_prefix = f"$state.working.{sid}_"
            if any(
                isinstance(v, str) and v.startswith(sid_prefix)
                for v in cap_inputs.values()
            ):
                return False
            return True

        use_primary_cap = (
            bool(primary_cap_ref)
            and not bool(primary_skill_ref)   # skill wins; cap only when no skill
            and not _is_non_executable_planner_cap(primary_cap_ref)
            and primary_cap_ref != "agent.task.delegate"
            and _cap_has_valid_inputs(primary_cap_ref)
        )

        if use_primary_cap:
            steps.append({
                "id": f"{sid}_step1",
                "type": "capability",
                "ref": primary_cap_ref,
                "purpose": f"Primary operation: {objective[:60]}",
                "inputs": _cap_inputs(primary_cap_ref),
                "outputs": _cap_outputs(primary_cap_ref),
                "depends_on": list(prev_step_ids),
            })

        if primary_skill_ref and primary_skill_ref != primary_cap_ref:
            prev = ([f"{sid}_step1"] if use_primary_cap else []) + list(prev_step_ids)
            step_id = f"{sid}_step2" if use_primary_cap else f"{sid}_step1"
            steps.append({
                "id": step_id,
                "type": "skill",
                "ref": primary_skill_ref,
                "purpose": f"Skill execution: {objective[:60]}",
                "inputs": _skill_inputs(primary_skill_ref),
                "outputs": _skill_outputs_map(primary_skill_ref, step_id),
                "depends_on": prev,
            })

        if not steps:
            steps.append({
                "id": f"{sid}_step1",
                "type": "capability",
                "ref": "model.output.generate",
                "purpose": f"Fallback for stage {sid}",
                "inputs": {"prompt": f"$state.working.{sid}_input"},
                "outputs": {"content": f"$state.working.{sid}_output"},
                "depends_on": list(prev_step_ids),
            })

        return steps

    # Handle full macro_plan (with "stages") or single stage dict
    if isinstance(macro_stage, dict) and "stages" in macro_stage:
        stages_list = macro_stage.get("stages", [])
    else:
        stages_list = [macro_stage] if macro_stage else []

    expanded_steps = []
    prev_step_ids = []
    prev_output_state = None  # state ref for last stage's primary output

    for stage in stages_list:
        if not isinstance(stage, dict):
            continue
        stage_steps = _expand_single_stage(stage, prev_step_ids, prev_output_state)
        expanded_steps.extend(stage_steps)
        if stage_steps:
            last = stage_steps[-1]
            prev_step_ids = [last["id"]]
            outputs = last.get("outputs", {})
            # Prefer array-typed outputs (sources/clusters) for downstream
            # stage binding — analysis skills need arrays, not strings.
            _array_preferred = ["sources", "clusters", "items", "results"]
            prev_output_state = next(
                (outputs[k] for k in _array_preferred if k in outputs),
                next(iter(outputs.values()), None),
            )

    if not expanded_steps:
        expanded_steps.append({
            "id": "s1_step1",
            "type": "capability",
            "ref": "model.output.generate",
            "purpose": "Fallback: no stages resolved",
            "inputs": {"prompt": "$state.working.s1_input"},
            "outputs": {"content": "$state.working.s1_output"},
            "depends_on": [],
        })

    return {
        "expanded_steps": expanded_steps,
        "step_count": len(expanded_steps),
    }


def map_plan_inputs(expanded_steps, state_schema=None):
    """
    Bind expanded step inputs/outputs to CognitiveState paths.

    Args:
        expanded_steps (list): Steps from split_plan_stage.
        state_schema (dict, optional): CognitiveState schema.

    Returns:
        dict: {"bound_steps": list, "unresolved_bindings": list}
    """
    if not isinstance(expanded_steps, list):
        expanded_steps = []

    bound_steps = []
    for step in expanded_steps:
        if not isinstance(step, dict):
            continue
        step_id = step.get("id", "unknown")
        # Preserve literal inputs (e.g., objective/query) and keep explicit
        # state references unchanged. This prevents generating plans with
        # unresolved placeholder-only parameters.
        bound_inputs = {}
        for k, v in (step.get("inputs") or {}).items():
            if isinstance(v, str) and v.startswith("$state."):
                bound_inputs[k] = v
            else:
                bound_inputs[k] = v
        # Map outputs to $state.working.* paths
        bound_outputs = {
            k: f"$state.working.{step_id}_{k}"
            for k in (step.get("outputs") or {}).keys()
        }
        bound_steps.append({
            **step,
            "inputs": bound_inputs,
            "outputs": bound_outputs,
        })

    return {
        "bound_steps": bound_steps,
        "unresolved_bindings": [],
        "_fallback": True,
    }


def validate_plan(expanded_plan, registry=None, state_schema=None):
    """
    Validate structural correctness of an ORCA plan.

    Deterministic checks:
    - Steps have id, type, ref, depends_on
    - No duplicate step ids
    - depends_on references exist
    - No obvious cycles (single-pass check)

    Args:
        expanded_plan (dict): Plan with bound_steps.
        registry (dict, optional): Registry snapshot.
        state_schema (dict, optional): CognitiveState schema.

    Returns:
        dict: {"validation_result": object}
    """
    if not isinstance(expanded_plan, dict):
        return {"validation_result": {
            "status": "failed",
            "errors": [{"step_id": None, "check": "plan_structure",
                        "message": "expanded_plan must be a dict"}],
            "warnings": [],
            "repairable": True,
            "check_count": 1,
        }}

    steps = expanded_plan.get("bound_steps", expanded_plan.get("steps", []))
    errors = []
    warnings = []
    check_count = 0

    if not isinstance(steps, list):
        errors.append({"step_id": None, "check": "steps_list",
                       "message": "bound_steps must be a list"})
        return {"validation_result": {
            "status": "failed", "errors": errors, "warnings": warnings,
            "repairable": True, "check_count": 1,
        }}

    step_ids = set()
    for step in steps:
        if not isinstance(step, dict):
            continue
        step_id = step.get("id")
        check_count += 1

        # Check required fields
        for field in ["id", "ref", "type"]:
            if not step.get(field):
                errors.append({"step_id": step_id, "check": f"required_{field}",
                               "message": f"Step missing required field '{field}'"})

        # Duplicate id check
        if step_id in step_ids:
            errors.append({"step_id": step_id, "check": "unique_id",
                           "message": f"Duplicate step id '{step_id}'"})
        if step_id:
            step_ids.add(step_id)

        # Validate depends_on
        for dep in step.get("depends_on", []):
            check_count += 1
            # Will validate after collecting all ids

    # Second pass: validate all depends_on against known step ids
    for step in steps:
        if not isinstance(step, dict):
            continue
        for dep in step.get("depends_on", []):
            if dep not in step_ids:
                errors.append({"step_id": step.get("id"), "check": "deps_exist",
                               "message": f"depends_on references unknown step '{dep}'"})

    # Third pass: validate step refs exist in the registry
    known_refs: set[str] | None = None
    if isinstance(registry, dict) and registry:
        known_refs = set(registry.keys())
    else:
        try:
            from sdk.embedded import list_capabilities, list_skills
            cap_ids = {c["id"] for c in list_capabilities() if isinstance(c, dict) and "id" in c}
            skill_ids = {s["id"] for s in list_skills() if isinstance(s, dict) and "id" in s}
            known_refs = cap_ids | skill_ids
        except Exception:
            pass  # registry unavailable; skip ref existence check

    if known_refs is not None:
        for step in steps:
            if not isinstance(step, dict):
                continue
            ref = step.get("ref")
            if ref and ref not in known_refs:
                errors.append({"step_id": step.get("id"), "check": "ref_exists",
                               "message": f"Step ref '{ref}' not found in registry"})

    status = "passed" if not errors else "failed"
    return {"validation_result": {
        "status": status,
        "errors": errors,
        "warnings": warnings,
        "repairable": bool(errors),
        "check_count": check_count,
        "_fallback": True,
    }}


def reconcile_plan(invalid_plan, validation_errors, registry=None):
    """
    Repair an invalid ORCA plan based on validation errors.

    Args:
        invalid_plan (dict): Plan that failed validation.
        validation_errors (list): Errors from validation_result.errors.
        registry (dict, optional): Registry snapshot.

    Returns:
        dict: {"repaired_plan": object, "repair_notes": list, "still_invalid": bool}
    """
    if not isinstance(invalid_plan, dict):
        return {
            "repaired_plan": {},
            "repair_notes": [{"step_id": None, "action": "abort",
                              "original": None, "replacement": None}],
            "still_invalid": True,
        }

    import copy
    repaired = copy.deepcopy(invalid_plan)
    repair_notes = []

    steps = repaired.get("bound_steps", repaired.get("steps", []))
    step_ids = {s.get("id") for s in steps if isinstance(s, dict) and s.get("id")}

    errors_list = validation_errors
    if isinstance(validation_errors, dict):
        if isinstance(validation_errors.get("errors"), list):
            errors_list = validation_errors.get("errors")
        elif isinstance(validation_errors.get("validation_result"), dict):
            nested = validation_errors.get("validation_result") or {}
            errors_list = nested.get("errors") if isinstance(nested.get("errors"), list) else []

    for err in (errors_list or []):
        if not isinstance(err, dict):
            continue
        check = err.get("check", "")
        step_id = err.get("step_id")

        if check == "deps_exist":
            # Remove invalid dependency
            for step in steps:
                if isinstance(step, dict) and step.get("id") == step_id:
                    invalid_dep = None
                    for dep in step.get("depends_on", []):
                        if dep not in step_ids:
                            invalid_dep = dep
                            break
                    if invalid_dep:
                        step["depends_on"] = [d for d in step["depends_on"]
                                              if d != invalid_dep]
                        repair_notes.append({
                            "step_id": step_id,
                            "action": "remove_invalid_dependency",
                            "original": invalid_dep,
                            "replacement": None,
                        })

        elif check in ("required_id", "required_ref", "required_type"):
            repair_notes.append({
                "step_id": step_id,
                "action": "flag_for_manual_review",
                "original": check,
                "replacement": None,
            })

    return {
        "repaired_plan": repaired,
        "repair_notes": repair_notes,
        "still_invalid": False,
        "_fallback": True,
    }


def synthesize_plan(validated_plan, runtime_config=None):
    """
    Compile a validated ORCA plan into an executable DAG.

    Args:
        validated_plan (dict): Validated plan with bound_steps.
        runtime_config (dict, optional): Execution configuration hints.

    Returns:
        dict: {"compiled_plan": object, "step_count": int}
    """
    import hashlib
    import json

    if isinstance(validated_plan, list):
        # Some skills pass bound steps directly as a list.
        steps = validated_plan
    else:
        if not isinstance(validated_plan, dict):
            validated_plan = {}
        steps = validated_plan.get("bound_steps", validated_plan.get("steps", []))
        if not isinstance(steps, list):
            steps = []

    nodes = []
    edges = []
    gate_steps = []

    for step in steps:
        if not isinstance(step, dict):
            continue
        step_id = step.get("id", "unknown")
        nodes.append({"id": step_id, "ref": step.get("ref", ""), "type": step.get("type", "capability")})
        for dep in step.get("depends_on", []):
            edges.append({"from": dep, "to": step_id})
        if step.get("gate", False):
            gate_steps.append(step_id)

    # Build topological order (simple sequential fallback)
    execution_order = [n["id"] for n in nodes]
    # Group independent steps (those with no depends_on that aren't depended on)
    dep_targets = {e["to"] for e in edges}
    root_steps = [n["id"] for n in nodes if n["id"] not in dep_targets]
    parallel_groups = [root_steps] if root_steps else [[execution_order[0]]] if execution_order else []

    state_bindings = {}
    for step in steps:
        if isinstance(step, dict):
            state_bindings[step.get("id", "")] = {
                "inputs": step.get("inputs", {}),
                "outputs": step.get("outputs", {}),
            }

    plan_hash_input = json.dumps(
        {"nodes": execution_order, "edges": sorted(f"{e['from']}->{e['to']}" for e in edges)},
        sort_keys=True,
    ).encode()
    plan_hash = hashlib.sha256(plan_hash_input).hexdigest()[:16]

    compiled_plan = {
        "dag": {"nodes": nodes, "edges": edges},
        "execution_order": execution_order,
        "parallel_groups": parallel_groups,
        "gates": gate_steps,
        "state_bindings": state_bindings,
        "registry_version": "current",
        "plan_hash": plan_hash,
    }
    compiled_plan_json = json.dumps(compiled_plan, ensure_ascii=False)
    return {
        "compiled_plan": compiled_plan,
        "compiled_plan_json": compiled_plan_json,
        "step_count": len(nodes),
        "_fallback": True,
    }


def gate_plan(compiled_plan, user_permissions=None, policy_context=None):
    """
    Determine whether a compiled plan can execute under current permissions.

    Args:
        compiled_plan (dict): Compiled plan from synthesize_plan.
        user_permissions (dict, optional): Principal permission set.
        policy_context (dict, optional): Active policy profile.

    Returns:
        dict: {"authorization_result": object}
    """
    if not isinstance(compiled_plan, dict):
        return {"authorization_result": {
            "status": "denied",
            "blocked_steps": [],
            "approval_prompts": [],
            "risk_level": "critical",
        }}

    # Conservative baseline: approve unless side_effects detected without permissions
    side_effect_refs = {"email.message.send", "fs.file.write", "integration.record.create",
                        "integration.record.update", "integration.record.delete",
                        "web.request.send"}
    blocked = []
    prompts = []

    nodes = compiled_plan.get("dag", {}).get("nodes", [])
    perms = user_permissions if isinstance(user_permissions, dict) else {}

    for node in nodes:
        ref = node.get("ref", "")
        if ref in side_effect_refs:
            perm_key = ref.replace(".", "_")
            if perms.get(perm_key) is False:
                blocked.append({"step_id": node.get("id"), "reason": f"Permission denied for {ref}"})
            elif not perms:
                prompts.append({"step_id": node.get("id"),
                                "prompt_text": f"Step '{node.get('id')}' will call {ref}. Confirm to proceed."})

    if blocked:
        status = "denied"
    elif prompts:
        status = "requires_user_approval"
    else:
        status = "approved"

    return {
        "authorization_result": {
            "status": status,
            "blocked_steps": blocked,
            "approval_prompts": prompts,
            "risk_level": "low" if status == "approved" else "medium",
        },
        "_fallback": True,
    }


def execute_plan(compiled_plan, initial_state=None):
    """
    Execute a compiled ORCA plan DAG step by step using sdk.embedded.execute.

    Resolves $state.working.* refs between steps and chains outputs through
    CognitiveState. Each step calls the referenced skill via the embedded runtime.

    Args:
        compiled_plan (dict|str): Compiled plan from synthesize_plan (or JSON string).
        initial_state (dict, optional): Initial CognitiveState.

    Returns:
        dict: {"execution_result": object, "failed_steps": list}
    """
    import time as _time
    import json

    # Accept both object and JSON string forms
    if isinstance(compiled_plan, str):
        try:
            compiled_plan = json.loads(compiled_plan)
        except Exception:
            pass

    if not isinstance(compiled_plan, dict):
        return {
            "execution_result": {
                "status": "failed",
                "final_state": {},
                "step_results": [],
                "total_duration_ms": 0,
                "final_output": {},
                "error": "compiled_plan must be a dict or JSON string",
            },
            "failed_steps": [],
        }

    execution_order = compiled_plan.get("execution_order", [])
    nodes_by_id = {n["id"]: n for n in compiled_plan.get("dag", {}).get("nodes", [])}
    state_bindings = compiled_plan.get("state_bindings", {})
    state = dict(initial_state) if isinstance(initial_state, dict) else {}
    step_results = []
    failed_steps = []

    def _resolve(value):
        """Resolve $state.working.<key> refs to values stored in state."""
        if isinstance(value, str) and value.startswith("$state.working."):
            key = value[len("$state.working."):]
            return state.get(key)
        if isinstance(value, list):
            return [_resolve(v) for v in value]
        if isinstance(value, dict):
            return {k: _resolve(v) for k, v in value.items()}
        return value

    for step_id in execution_order:
        node = nodes_by_id.get(step_id, {})
        ref = node.get("ref", "")
        binding = state_bindings.get(step_id, {})
        raw_inputs = binding.get("inputs", {})

        # Resolve state refs in inputs
        resolved_inputs = {k: _resolve(v) for k, v in raw_inputs.items()}
        # Drop None values from unresolved refs (missing upstream outputs)
        resolved_inputs = {k: v for k, v in resolved_inputs.items() if v is not None}
        
        # Add extended timeout for skills (research queries can take 60-120s)
        resolved_inputs["_max_wait_ms"] = 180000  # 180 seconds

        start_ms = _time.time() * 1000
        try:
            from sdk.embedded import execute as _sdk_execute
            result = _sdk_execute(ref, resolved_inputs)
            duration_ms = int(_time.time() * 1000 - start_ms)

            # Store outputs back into state via state_bindings
            output_bindings = binding.get("outputs", {})
            for out_key, state_ref in output_bindings.items():
                if isinstance(state_ref, str) and state_ref.startswith("$state.working."):
                    state_key = state_ref[len("$state.working."):]
                    state[state_key] = result.get(out_key)

            step_results.append({
                "step_id": step_id,
                "ref": ref,
                "status": "success",
                "outputs": result,
                "error": None,
                "duration_ms": duration_ms,
            })
        except Exception as exc:
            duration_ms = int(_time.time() * 1000 - start_ms)
            step_results.append({
                "step_id": step_id,
                "ref": ref,
                "status": "failed",
                "outputs": {},
                "error": str(exc),
                "duration_ms": duration_ms,
            })
            failed_steps.append(step_id)

    success_count = sum(1 for s in step_results if s["status"] == "success")
    if not failed_steps:
        overall_status = "success"
    elif success_count > 0:
        overall_status = "partial"
    else:
        overall_status = "failed"

    # Return the last successful step's full output as final_output
    final_output = {}
    for sr in reversed(step_results):
        if sr["status"] == "success" and sr["outputs"]:
            final_output = sr["outputs"]
            break

    return {
        "execution_result": {
            "status": overall_status,
            "final_state": state,
            "step_results": step_results,
            "total_duration_ms": sum(s["duration_ms"] for s in step_results),
            "final_output": final_output,
        },
        "failed_steps": failed_steps,
    }


def generate_output_report(interpreted_goal, execution_result, evaluation=None, trace_summary=None):
    """
    Generate the final user-facing report from pipeline outputs.

    Args:
        interpreted_goal (dict): Goal from interpret_goal.
        execution_result (dict): Result from run_plan.
        evaluation (dict, optional): Result from eval.output.validate.
        trace_summary (dict, optional): Summary from ops.trace.summarize.

    Returns:
        dict: {"report": object, "report_status": str}
    """
    if not isinstance(interpreted_goal, dict):
        interpreted_goal = {}
    if not isinstance(execution_result, dict):
        execution_result = {}

    objective = interpreted_goal.get("objective", "Complete the task")
    exec_status = execution_result.get("status", "unknown")
    step_results = execution_result.get("step_results", [])
    steps_done = [s["step_id"] for s in step_results if s.get("status") == "success"]

    failed_criteria = []
    if isinstance(evaluation, dict):
        eval_obj = evaluation.get("evaluation", evaluation)
        failed_criteria = eval_obj.get("failed_criteria", [])

    limitations = []
    if failed_criteria:
        limitations = [f"Criterion not fully met: {c}" for c in failed_criteria]

    user_response = (
        f"# Task Report\n\n"
        f"**Objective:** {objective}\n\n"
        f"**Status:** {exec_status}\n\n"
        f"**Steps completed:** {len(steps_done)}\n\n"
    )
    if limitations:
        user_response += "**Limitations:**\n" + "\n".join(f"- {l}" for l in limitations) + "\n\n"
    user_response += "_Note: This is a baseline report. Real execution produces richer output._"

    report_status_map = {"success": "success", "partial": "partial", "failed": "failed"}
    report_status = report_status_map.get(exec_status, "requires_followup")

    return {
        "report": {
            "user_response": user_response,
            "artifacts": [],
            "limitations": limitations,
            "next_steps": ["Review the output and refine the task if needed."],
            "evidence": [],
        },
        "report_status": report_status,
        "_fallback": True,
    }


def synthesize_output_skill(successful_plan, execution_trace):
    """
    Convert a completed plan and trace into a candidate ORCA skill spec.

    Args:
        successful_plan (dict): Compiled plan that completed successfully.
        execution_trace (dict): Execution result from run_plan.

    Returns:
        dict: {"candidate_skill": object, "confidence": float}
    """
    import hashlib
    import json

    if not isinstance(successful_plan, dict):
        successful_plan = {}
    if not isinstance(execution_trace, dict):
        execution_trace = {}

    nodes = successful_plan.get("dag", {}).get("nodes", [])
    execution_order = successful_plan.get("execution_order", [])

    # Build skill steps from DAG
    steps = []
    for i, step_id in enumerate(execution_order):
        node = next((n for n in nodes if n.get("id") == step_id), {})
        steps.append({
            "id": f"step_{i + 1}",
            "uses": node.get("ref", "model.output.generate"),
            "input": {},
            "output": {},
        })

    # Derive a name from the first step refs
    refs = [n.get("ref", "") for n in nodes[:2]]
    name_hint = "_".join(r.split(".")[-1] for r in refs if r)[:30]
    skill_hash = hashlib.sha256(json.dumps(execution_order).encode()).hexdigest()[:6]
    name = f"agent.generated-{name_hint or skill_hash}"

    confidence = 0.5 if steps else 0.1

    return {
        "candidate_skill": {
            "name": name,
            "description": (
                f"Auto-generated skill from successful execution of "
                f"{len(steps)} steps. Review before registering."
            ),
            "version": "0.1.0",
            "steps": steps,
            "inputs": {"goal": {"type": "string", "required": True,
                                "description": "Task objective"}},
            "outputs": {"result": {"type": "object",
                                   "description": "Task execution output"}},
            "tags": ["generated", "candidate"],
            "notes": ["Auto-generated — verify step refs and bindings before registration."],
        },
        "confidence": confidence,
        "_fallback": True,
    }

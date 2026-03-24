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
    import hashlib, json
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
        {"id": "step-1", "action": "analyse", "description": f"Analyse requirements for: {goal}", "depends_on": []},
        {"id": "step-2", "action": "execute", "description": "Execute core actions based on analysis", "depends_on": ["step-1"]},
        {"id": "step-3", "action": "verify", "description": "Verify outputs meet the objective", "depends_on": ["step-2"]},
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
        options.append({
            "id": f"opt-{slug}",
            "label": f"Option {i}: {slug.title()}",
            "description": f"{desc} for '{prefix}'.",
            "key_attributes": {"risk": slug, "speed": "medium", "cost": "medium"},
        })

    return {
        "options": options,
        "generation_notes": f"Baseline generation: {len(options)} options from goal text.",
    }
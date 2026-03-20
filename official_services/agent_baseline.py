"""
Agent baseline service module.
Provides baseline implementations for agent-related capabilities.
"""

def delegate_agent(task, agent):
    """
    Delegate a task to an agent.
    
    Args:
        task (str): The task description.
        agent (str): The agent identifier.
    
    Returns:
        dict: {"accepted": bool}
    """
    # Baseline implementation: always accept
    return {"accepted": True}

def generate_plan(goal):
    """
    Generate a plan for achieving a goal.
    
    Args:
        goal (str): The goal description.
    
    Returns:
        dict: {"plan": object}  — matches schema type
    """
    # Baseline implementation: structured plan object
    return {"plan": {"objective": goal, "steps": [f"Step 1: Analyse requirements for: {goal}", "Step 2: Execute", "Step 3: Verify"]}}

def route_agent(query, agents):
    """
    Route a query to the most appropriate agent.

    Args:
        query (str): The query text.
        agents (list): List of available agents.

    Returns:
        dict: {"route": str}
    """
    # Baseline implementation: select first agent or derive route from query
    if isinstance(agents, list) and agents:
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
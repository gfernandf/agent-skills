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
    # Baseline implementation: select first agent
    selected = agents[0] if agents else "default"
    return {"route": selected}
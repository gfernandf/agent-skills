"""
Analysis baseline service module.
Provides baseline implementations for analysis-domain capabilities.
"""

from __future__ import annotations


def split_problem(problem, strategy, context=None, max_components=None):
    """
    Split a complex problem into manageable components.

    Baseline heuristic: generates 3-4 components based on the strategy axis,
    with sequential dependencies and no detected gaps/overlaps.
    """
    if max_components is None:
        max_components = 6

    strategy = strategy or "themes"
    prefix = problem[:60] if problem else "problem"

    component_count = min(max_components, 4)
    components = []
    for i in range(1, component_count + 1):
        comp = {
            "id": f"c{i}",
            "label": f"Component {i} ({strategy})",
            "description": f"Dimension {i} of '{prefix}' decomposed by {strategy}.",
            "dependencies": [f"c{i-1}"] if i > 1 else [],
            "analysis_order": i,
        }
        components.append(comp)

    return {
        "components": components,
        "gaps": [],
        "overlaps": [],
        "decomposition_notes": f"Baseline decomposition by {strategy} into {component_count} components.",
    }


def extract_risks(target, context=None, risk_scope=None):
    """
    Extract risks, assumptions, failure modes, and mitigation ideas.

    Baseline heuristic: emits 2 generic risks, 1 assumption, 1 failure mode.
    """
    scope = risk_scope or "broad"

    risks = [
        {
            "id": "r1",
            "description": f"Incomplete information may lead to suboptimal outcomes ({scope} scope).",
            "category": "operational",
            "severity_hint": "medium",
            "related_assumptions": ["a1"],
        },
        {
            "id": "r2",
            "description": "External conditions may change after analysis.",
            "category": "strategic",
            "severity_hint": "low",
            "related_assumptions": [],
        },
    ]

    assumptions = [
        {
            "id": "a1",
            "statement": "Available information is representative and current.",
            "fragility_hint": "medium",
            "related_risks": ["r1"],
        },
    ]

    failure_modes = [
        {
            "id": "f1",
            "description": "Target artifact relies on an assumption that turns out false.",
            "trigger_conditions": "Assumption a1 is invalidated by new data.",
            "related_risks": ["r1"],
        },
    ]

    mitigation_ideas = [
        {"risk_id": "r1", "suggestion": "Validate key inputs before proceeding.", "effort_hint": "low"},
    ]

    return {
        "risks": risks,
        "assumptions": assumptions,
        "failure_modes": failure_modes,
        "mitigation_ideas": mitigation_ideas,
        "extraction_notes": f"Baseline extraction with {scope} scope.",
    }

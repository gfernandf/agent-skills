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
        "extraction_notes": f"Baseline fallback extraction ({scope} scope). These are generic placeholder risks — use the OpenAI binding for content-specific analysis.",
        "_fallback": True,
    }


def cluster_themes(items, hint_labels=None, max_clusters=None, context=None):
    """
    Group items into thematic clusters.

    Baseline heuristic: assigns items round-robin to hint_labels (or generic
    themes). Each cluster gets a summary built from its items' content.
    Production bindings should use an LLM or embedding-based clustering.
    """
    if max_clusters is None:
        max_clusters = 8
    max_clusters = min(max_clusters, 15)

    if not items:
        return {"clusters": [], "unclustered": [], "cluster_quality": {
            "coherence_score": 0.0, "coverage_ratio": 0.0, "overlap_warnings": [],
        }}

    # Determine theme labels
    if hint_labels and len(hint_labels) > 0:
        labels = list(hint_labels[:max_clusters])
    else:
        n = min(len(items), max_clusters, 5)
        labels = [f"theme_{i+1}" for i in range(n)]

    # Build cluster buckets
    buckets = {label: [] for label in labels}
    for idx, item in enumerate(items):
        target = labels[idx % len(labels)]
        buckets[target].append(item)

    clusters = []
    for label in labels:
        bucket_items = buckets[label]
        if not bucket_items:
            continue
        # Build summary from item content
        snippets = []
        item_ids = []
        for it in bucket_items:
            item_ids.append(it.get("id", f"item_{id(it)}"))
            content = it.get("content", "")
            if content:
                snippets.append(content[:200])

        summary = "; ".join(snippets) if snippets else "No content available."
        clusters.append({
            "theme": label,
            "description": f"Cluster for theme '{label}' containing {len(bucket_items)} items.",
            "item_ids": item_ids,
            "summary": summary,
            "signal_strength": round(len(bucket_items) / len(items), 2),
        })

    assigned_ids = set()
    for c in clusters:
        assigned_ids.update(c["item_ids"])

    unclustered = []
    for it in items:
        iid = it.get("id", f"item_{id(it)}")
        if iid not in assigned_ids:
            unclustered.append({"id": iid, "reason": "No matching theme."})

    coverage = len(assigned_ids) / len(items) if items else 0.0

    return {
        "clusters": clusters,
        "unclustered": unclustered,
        "cluster_quality": {
            "coherence_score": 0.6,
            "coverage_ratio": round(coverage, 2),
            "overlap_warnings": [],
        },
    }

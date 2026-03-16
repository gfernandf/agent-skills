"""
Ops baseline service module.
Provides baseline implementations for budget estimation and trace monitoring.
"""

from __future__ import annotations


def estimate_budget(plan, limits=None):
    if not isinstance(plan, dict):
        return {
            "estimated_cost": 0.0,
            "estimated_duration_ms": 0.0,
            "within_budget": False,
        }

    steps = plan.get("steps", [])
    step_count = len(steps) if isinstance(steps, list) else 1

    estimated_cost = round(step_count * 0.01, 4)
    estimated_duration_ms = float(step_count * 500)

    within_budget = True
    if isinstance(limits, dict):
        max_cost = limits.get("max_cost")
        max_duration_ms = limits.get("max_duration_ms")
        if isinstance(max_cost, (int, float)) and estimated_cost > float(max_cost):
            within_budget = False
        if isinstance(max_duration_ms, (int, float)) and estimated_duration_ms > float(max_duration_ms):
            within_budget = False

    return {
        "estimated_cost": estimated_cost,
        "estimated_duration_ms": estimated_duration_ms,
        "within_budget": within_budget,
    }


def monitor_trace(trace, thresholds=None):
    if not isinstance(trace, dict):
        return {"status": "invalid", "alerts": ["trace_must_be_object"]}

    alerts = []
    status = "ok"

    duration_ms = trace.get("duration_ms")
    error_count = trace.get("error_count", 0)

    if isinstance(thresholds, dict):
        max_duration_ms = thresholds.get("max_duration_ms")
        max_errors = thresholds.get("max_errors")

        if isinstance(duration_ms, (int, float)) and isinstance(max_duration_ms, (int, float)):
            if duration_ms > max_duration_ms:
                alerts.append("duration_threshold_exceeded")

        if isinstance(error_count, (int, float)) and isinstance(max_errors, (int, float)):
            if error_count > max_errors:
                alerts.append("error_threshold_exceeded")

    if alerts:
        status = "alert"

    return {"status": status, "alerts": alerts}


def analyze_trace(
    goal,
    events,
    context=None,
    trace_state=None,
    trace_session_id=None,
    state_mode=None,
    mode=None,
    output_views=None,
    thresholds=None,
):
    import hashlib
    import json
    import uuid

    session_id = trace_session_id or str(uuid.uuid4())
    events_list = events if isinstance(events, list) else []
    prior_state = trace_state if isinstance(trace_state, dict) else {}

    accumulated_events = prior_state.get("events", []) + events_list
    step_ids = [e.get("step_id") for e in accumulated_events if isinstance(e, dict) and e.get("step_id")]
    error_events = [e for e in accumulated_events if isinstance(e, dict) and e.get("type") == "error"]

    updated_state = {
        "goal": goal,
        "events": accumulated_events,
        "error_count": len(error_events),
        "cycle": prior_state.get("cycle", 0) + 1,
    }
    state_bytes = json.dumps(updated_state, sort_keys=True).encode("utf-8")
    state_checksum = hashlib.sha256(state_bytes).hexdigest()[:16]

    requested_views = output_views if isinstance(output_views, list) else []

    decision_graph = None
    if not requested_views or "decision_graph" in requested_views:
        decision_graph = {
            "nodes": [{"id": sid, "type": "step"} for sid in step_ids],
            "edges": [
                {"from": step_ids[i], "to": step_ids[i + 1]}
                for i in range(len(step_ids) - 1)
            ],
        }

    assumptions = None
    if not requested_views or "assumptions" in requested_views:
        assumptions = [{"source": "baseline", "assumption": f"goal_is_feasible: {bool(goal)}"}]

    alternative_paths = None
    if not requested_views or "alternative_paths" in requested_views:
        alternative_paths = []

    confidence = max(0.0, 1.0 - (len(error_events) * 0.1))

    summary = None
    if not requested_views or "summary" in requested_views:
        mode_label = mode or "update"
        summary = (
            f"Trace analysis ({mode_label}): {len(accumulated_events)} events processed, "
            f"{len(error_events)} errors, confidence {confidence:.2f}."
        )

    return {
        "trace_session_id": session_id,
        "updated_trace_state": updated_state,
        "state_checksum": state_checksum,
        "trace_version": "1.0.0",
        "decision_graph": decision_graph,
        "assumptions": assumptions,
        "alternative_paths": alternative_paths,
        "confidence": confidence,
        "risk_candidates": [],
        "summary": summary,
    }

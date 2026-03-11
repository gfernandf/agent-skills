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

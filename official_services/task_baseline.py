"""
Task baseline service module.
Provides baseline implementations for case, approval, incident, and SLA operations.
Uses an in-memory store for local testing.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

# ── In-memory stores ──

_CASE_COUNTER = 0
_CASES: dict[str, dict] = {}
_APPROVALS: dict[str, dict] = {}
_INCIDENTS: dict[str, dict] = {}
_MILESTONES: dict[str, dict] = {}
_EVENTS: dict[str, dict] = {}

# Allowed state transitions
_STATE_TRANSITIONS: dict[str, list[str]] = {
    "open": ["in_progress", "closed", "blocked"],
    "in_progress": ["open", "closed", "blocked", "review"],
    "review": ["in_progress", "closed"],
    "blocked": ["open", "in_progress"],
    "closed": ["open"],  # re-open allowed
}


def _next_id(prefix: str) -> str:
    global _CASE_COUNTER
    _CASE_COUNTER += 1
    return f"{prefix}-{_CASE_COUNTER}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Approval operations ──


def approve_request(approval_id, approver=None, notes=None):
    _APPROVALS[str(approval_id)] = {"status": "approved", "approver": approver, "notes": notes}
    return {"approved": True, "timestamp": _now()}


def reject_request(approval_id, rejector=None, reason=""):
    _APPROVALS[str(approval_id)] = {"status": "rejected", "rejector": rejector, "reason": reason}
    return {"rejected": True, "timestamp": _now()}


# ── Assignment ──


def assign_task(task_id, assignee_id):
    case = _CASES.get(str(task_id))
    if case:
        case["assignee"] = str(assignee_id)
    return {"assigned": True, "timestamp": _now()}


# ── Case CRUD ──


def create_case(title, description=None, priority=None):
    case_id = _next_id("CASE")
    case = {
        "id": case_id,
        "title": str(title),
        "description": str(description) if description else "",
        "priority": str(priority) if priority else "medium",
        "status": "open",
        "assignee": None,
        "created_at": _now(),
    }
    _CASES[case_id] = case
    return {"case_id": case_id, "created": True}


def get_case(case_id):
    case = _CASES.get(str(case_id))
    if case:
        return {"case": case, "found": True}
    return {"case": {"id": str(case_id)}, "found": False}


def list_cases(status_filter=None, assignee_filter=None):
    cases = list(_CASES.values())
    if status_filter:
        cases = [c for c in cases if c.get("status") == str(status_filter)]
    if assignee_filter:
        cases = [c for c in cases if c.get("assignee") == str(assignee_filter)]
    return {"cases": cases, "total": len(cases)}


def search_cases(query, filters=None):
    q = str(query).lower()
    results = []
    for case in _CASES.values():
        text = f"{case.get('title', '')} {case.get('description', '')}".lower()
        if q in text:
            if isinstance(filters, dict):
                if filters.get("status") and case.get("status") != filters["status"]:
                    continue
                if filters.get("priority") and case.get("priority") != filters["priority"]:
                    continue
            results.append(case)
    return {"results": results, "total": len(results)}


def update_case(case_id, fields):
    case = _CASES.get(str(case_id))
    if case and isinstance(fields, dict):
        case.update(fields)
        return {"updated": True}
    return {"updated": False}


def close_case(case_id, resolution=None):
    case = _CASES.get(str(case_id))
    if case:
        case["status"] = "closed"
        case["resolution"] = str(resolution) if resolution else "resolved"
        case["closed_at"] = _now()
        return {"closed": True, "timestamp": _now()}
    return {"closed": False, "timestamp": _now()}


# ── Event ──


def acknowledge_event(event_id, handler=None):
    _EVENTS[str(event_id)] = {"acknowledged": True, "handler": handler}
    return {"acknowledged": True, "timestamp": _now()}


# ── Incident ──


def create_incident(title, severity, affected_system=None, description=None):
    iid = _next_id("INC")
    incident = {
        "id": iid,
        "title": str(title),
        "severity": str(severity),
        "affected_system": str(affected_system) if affected_system else None,
        "description": str(description) if description else "",
        "status": "open",
        "created_at": _now(),
    }
    _INCIDENTS[iid] = incident
    # Also create as a case
    _CASES[iid] = {**incident, "priority": severity}
    return {"incident_id": iid, "created": True}


# ── Milestone ──


def schedule_milestone(milestone_name, target_date, deliverables=None):
    mid = _next_id("MS")
    milestone = {
        "id": mid,
        "name": str(milestone_name),
        "target_date": str(target_date),
        "deliverables": deliverables if isinstance(deliverables, list) else [],
        "status": "scheduled",
    }
    _MILESTONES[mid] = milestone
    return {"milestone_id": mid, "scheduled": True}


# ── Priority classification ──


def classify_priority(task, context=None):
    if not isinstance(task, dict):
        return {"priority": "medium", "confidence": 0.5, "rationale": "No task data provided."}

    text = f"{task.get('title', '')} {task.get('description', '')}".lower()
    score = 0

    critical_pats = [r'\b(outage|down|breach|data.?loss|p0|sev.?1)\b']
    high_pats = [r'\b(urgent|blocker|escalat|security|production)\b']
    medium_pats = [r'\b(important|deadline|customer|regression)\b']

    for pat in critical_pats:
        if re.search(pat, text):
            score += 3
    for pat in high_pats:
        if re.search(pat, text):
            score += 2
    for pat in medium_pats:
        if re.search(pat, text):
            score += 1

    if isinstance(context, dict):
        if context.get("sla_tier") in ("platinum", "gold"):
            score += 1
        if isinstance(context.get("impacted_users"), (int, float)) and context["impacted_users"] > 1000:
            score += 1

    if score >= 3:
        priority = "critical"
    elif score >= 2:
        priority = "high"
    elif score >= 1:
        priority = "medium"
    else:
        priority = "low"

    confidence = min(score / 4.0, 1.0) if score > 0 else 0.6
    rationale = f"Keyword heuristic scored {score}." if score > 0 else "No priority indicators detected."

    return {"priority": priority, "confidence": round(confidence, 3), "rationale": rationale}


# ── SLA monitoring ──


def monitor_sla(tasks, sla_rules):
    task_list = tasks if isinstance(tasks, list) else []
    rules = sla_rules if isinstance(sla_rules, dict) else {}

    compliant = []
    breached = []
    at_risk = []
    now = datetime.now(timezone.utc)

    for t in task_list:
        if not isinstance(t, dict):
            continue
        priority = str(t.get("priority", "medium"))
        max_hours = rules.get(priority)
        if not isinstance(max_hours, (int, float)):
            compliant.append(t)
            continue

        created = t.get("created_at", "")
        try:
            created_dt = datetime.fromisoformat(str(created).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            compliant.append(t)
            continue

        elapsed_hours = (now - created_dt).total_seconds() / 3600
        if elapsed_hours > max_hours:
            breached.append(t)
        elif elapsed_hours > max_hours * 0.8:
            at_risk.append(t)
        else:
            compliant.append(t)

    return {"compliant": compliant, "breached": breached, "at_risk": at_risk}


# ── State transition ──


def transition_state(task_id, target_state):
    case = _CASES.get(str(task_id))
    if not case:
        # Create a virtual case to still return a meaningful response
        return {
            "transitioned": True,
            "previous_state": "open",
            "current_state": str(target_state),
            "reason": None,
        }

    current = case.get("status", "open")
    allowed = _STATE_TRANSITIONS.get(current, [])

    if str(target_state) in allowed or str(target_state) == current:
        prev = current
        case["status"] = str(target_state)
        return {
            "transitioned": True,
            "previous_state": prev,
            "current_state": str(target_state),
            "reason": None,
        }
    else:
        return {
            "transitioned": False,
            "previous_state": current,
            "current_state": current,
            "reason": f"Transition from '{current}' to '{target_state}' not allowed. Allowed: {allowed}.",
        }

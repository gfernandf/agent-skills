"""
Identity baseline service module.
Provides baseline implementations for identity, role, and permission operations.
Uses an in-memory directory for local testing.
"""

from __future__ import annotations

# ── In-memory directory ──

_ROLES: dict[str, dict] = {
    "admin": {
        "id": "admin",
        "name": "Administrator",
        "description": "Full system access",
        "permissions": ["system:admin", "resource:read", "resource:write", "resource:delete"],
    },
    "editor": {
        "id": "editor",
        "name": "Editor",
        "description": "Can read and write resources",
        "permissions": ["resource:read", "resource:write"],
    },
    "viewer": {
        "id": "viewer",
        "name": "Viewer",
        "description": "Read-only access",
        "permissions": ["resource:read"],
    },
}

_PRINCIPALS: dict[str, dict] = {
    "alice": {"id": "alice", "name": "Alice", "roles": ["admin"], "skills": ["python", "devops"], "workload": 3},
    "bob": {"id": "bob", "name": "Bob", "roles": ["editor"], "skills": ["frontend", "design"], "workload": 5},
    "carol": {"id": "carol", "name": "Carol", "roles": ["viewer"], "skills": ["python", "ml"], "workload": 1},
}

_PERMISSIONS: dict[str, dict] = {
    "system:admin": {"id": "system:admin", "description": "Full system administration", "resource": "system", "action": "admin"},
    "resource:read": {"id": "resource:read", "description": "Read resources", "resource": "resource", "action": "read"},
    "resource:write": {"id": "resource:write", "description": "Write resources", "resource": "resource", "action": "write"},
    "resource:delete": {"id": "resource:delete", "description": "Delete resources", "resource": "resource", "action": "delete"},
}


# ── Public functions ──


def identify_assignee(task, candidates=None):
    pool = candidates if isinstance(candidates, list) else list(_PRINCIPALS.values())
    if not isinstance(task, dict):
        return {"assignee": pool[0] if pool else {}, "alternatives": [], "rationale": "No task provided; returning first candidate."}

    required_skills = set(task.get("required_skills", []))
    scored = []
    for c in pool:
        c = c if isinstance(c, dict) else _PRINCIPALS.get(str(c), {"id": str(c), "skills": [], "workload": 5})
        skills = set(c.get("skills", []))
        overlap = len(required_skills & skills) if required_skills else 1
        workload_penalty = c.get("workload", 5) * 0.1
        score = round(overlap - workload_penalty, 3)
        scored.append({"candidate": c, "score": score})

    scored.sort(key=lambda x: x["score"], reverse=True)
    best = scored[0] if scored else {"candidate": {}, "score": 0}

    return {
        "assignee": {**best["candidate"], "match_score": best["score"]},
        "alternatives": [{"id": s["candidate"].get("id"), "match_score": s["score"]} for s in scored[1:3]],
        "rationale": f"Selected based on skill overlap and workload. Score: {best['score']}.",
    }


def justify_decision(decision, subject, policies=None):
    policies_list = policies if isinstance(policies, list) else []
    applicable = [p for p in policies_list if isinstance(p, dict)] or [{"id": "default", "description": "Default identity policy"}]

    return {
        "justification": f"Decision '{decision}' for subject '{subject.get('id', subject) if isinstance(subject, dict) else subject}' based on {len(applicable)} policy(ies).",
        "applicable_policies": applicable,
        "confidence": round(min(len(applicable) / 3.0, 1.0), 3),
    }


def gate_permission(principal_id, permission, context=None):
    principal = _PRINCIPALS.get(str(principal_id))
    if not principal:
        return {"allowed": False, "reason": f"Principal '{principal_id}' not found."}

    effective = _get_effective_permissions(principal)
    if str(permission) in effective:
        return {"allowed": True, "reason": f"Permission '{permission}' granted via role."}
    return {"allowed": False, "reason": f"Principal '{principal_id}' does not hold '{permission}'."}


def get_permission(permission_id):
    perm = _PERMISSIONS.get(str(permission_id))
    if perm:
        return {"permission": perm, "found": True}
    return {"permission": {"id": str(permission_id)}, "found": False}


def list_permissions(principal_id, resource_filter=None):
    principal = _PRINCIPALS.get(str(principal_id))
    if not principal:
        return {"permissions": [], "total": 0}

    effective = _get_effective_permissions(principal)
    perms = [_PERMISSIONS.get(p, {"id": p}) for p in effective]

    if resource_filter:
        perms = [p for p in perms if str(p.get("resource", "")).startswith(str(resource_filter))]

    return {"permissions": perms, "total": len(perms)}


def verify_permission(principal_id, permission):
    principal = _PRINCIPALS.get(str(principal_id))
    if not principal:
        return {"verified": False, "source": "none", "evidence": {}}

    for role_id in principal.get("roles", []):
        role = _ROLES.get(role_id, {})
        if str(permission) in role.get("permissions", []):
            return {"verified": True, "source": "role-inherited", "evidence": {"role": role_id}}

    return {"verified": False, "source": "none", "evidence": {}}


def score_risk(principal_id, signals=None):
    signals = signals if isinstance(signals, dict) else {}
    factors = []
    score = 0.0

    if signals.get("login_failures", 0) > 3:
        factors.append("high_login_failures")
        score += 0.3
    if signals.get("unusual_hours"):
        factors.append("unusual_hours")
        score += 0.2
    if signals.get("geo_anomaly"):
        factors.append("geo_anomaly")
        score += 0.3
    if signals.get("privilege_escalation"):
        factors.append("privilege_escalation")
        score += 0.2

    score = round(min(score, 1.0), 3)
    return {"risk_score": score, "factors": factors, "safe": score < 0.5}


def assign_role(principal_id, role_id):
    principal = _PRINCIPALS.get(str(principal_id))
    if not principal:
        _PRINCIPALS[str(principal_id)] = {"id": str(principal_id), "name": str(principal_id), "roles": [str(role_id)], "skills": [], "workload": 0}
    else:
        if str(role_id) not in principal.get("roles", []):
            principal.setdefault("roles", []).append(str(role_id))

    role = _ROLES.get(str(role_id), {})
    return {"assigned": True, "effective_permissions": role.get("permissions", [])}


def get_role(role_id):
    role = _ROLES.get(str(role_id))
    if role:
        return {"role": role, "found": True}
    return {"role": {"id": str(role_id)}, "found": False}


def list_roles(scope=None):
    roles = list(_ROLES.values())
    if scope:
        roles = [r for r in roles if scope in r.get("tags", []) or scope in r.get("description", "").lower()]
    return {"roles": roles, "total": len(roles)}


# ── Helpers ──


def _get_effective_permissions(principal):
    perms = set()
    for role_id in principal.get("roles", []):
        role = _ROLES.get(role_id, {})
        perms.update(role.get("permissions", []))
    return perms

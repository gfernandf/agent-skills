#!/usr/bin/env python3
"""Smoke test for customer-facing HTTP API."""

import urllib.request
import urllib.error
import json

BASE = "http://127.0.0.1:8080"
KEY = "test-key-2026"
results = []


def get(path, auth=True):
    headers = {"x-api-key": KEY} if auth else {}
    req = urllib.request.Request(f"{BASE}{path}", headers=headers)
    return urllib.request.urlopen(req, timeout=10)


def post(path, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=data,
        headers={"x-api-key": KEY, "Content-Type": "application/json"},
    )
    return urllib.request.urlopen(req, timeout=30)


# 1. Health (no auth)
try:
    r = get("/v1/health", auth=False)
    d = json.loads(r.read())
    results.append(
        ("GET /v1/health", r.status, "OK" if d.get("status") == "ok" else "UNEXPECTED")
    )
except Exception as e:
    results.append(("GET /v1/health", "ERR", str(e)[:80]))

# 2. OpenAPI spec (no auth)
try:
    r = get("/openapi.json", auth=False)
    d = json.loads(r.read())
    paths = list(d.get("paths", {}).keys())
    ver = d.get("openapi", "?")
    results.append(
        ("GET /openapi.json", r.status, f"{len(paths)} paths, openapi {ver}")
    )
except Exception as e:
    results.append(("GET /openapi.json", "ERR", str(e)[:80]))

# 3. Skill list
try:
    r = get("/v1/skills/list")
    d = json.loads(r.read())
    skills = d.get("skills", d) if isinstance(d, dict) else d
    count = len(skills) if isinstance(skills, list) else "?"
    results.append(("GET /v1/skills/list", r.status, f"{count} skills"))
except Exception as e:
    results.append(("GET /v1/skills/list", "ERR", str(e)[:80]))

# 4. Skill describe
try:
    r = get("/v1/skills/task.frame/describe")
    d = json.loads(r.read())
    results.append(
        ("GET /v1/skills/task.frame/describe", r.status, f"name={d.get('name', '?')}")
    )
except Exception as e:
    results.append(("GET /v1/skills/task.frame/describe", "ERR", str(e)[:80]))

# 5. Auth rejection (no key)
try:
    r = get("/v1/skills/list", auth=False)
    results.append(("GET /v1/skills/list (no key)", r.status, "SHOULD HAVE BEEN 401"))
except urllib.error.HTTPError as e:
    status_text = "REJECTED" if e.code == 401 else f"UNEXPECTED {e.code}"
    results.append(("GET /v1/skills/list (no key)", e.code, status_text))
except Exception as e:
    results.append(("GET /v1/skills/list (no key)", "ERR", str(e)[:80]))

# 6. Capability execute (pythoncall baseline)
try:
    r = post(
        "/v1/capabilities/text.content.classify/execute",
        {
            "inputs": {
                "text": "The server is running perfectly",
                "labels": ["positive", "negative"],
                "context": "",
            }
        },
    )
    d = json.loads(r.read())
    outputs = d.get("outputs", d)
    label = outputs.get("label", "?")
    results.append(("POST /capabilities/.../execute", r.status, f"label={label}"))
except Exception as e:
    results.append(("POST /capabilities/.../execute", "ERR", str(e)[:80]))

# 7. Capability explain
try:
    r = post("/v1/capabilities/text.content.summarize/explain", {})
    d = json.loads(r.read())
    binding = d.get("selected_binding", "?")
    results.append(("POST /capabilities/.../explain", r.status, f"binding={binding}"))
except Exception as e:
    results.append(("POST /capabilities/.../explain", "ERR", str(e)[:80]))

# 8. Governance
try:
    r = get("/v1/skills/governance")
    d = json.loads(r.read())
    items = d.get("skills", d) if isinstance(d, dict) else d
    count = len(items) if isinstance(items, list) else "?"
    results.append(("GET /v1/skills/governance", r.status, f"{count} entries"))
except Exception as e:
    results.append(("GET /v1/skills/governance", "ERR", str(e)[:80]))

print()
print("=" * 70)
print("  CUSTOMER-FACING API SMOKE TEST")
print("=" * 70)
passed = 0
for name, status, detail in results:
    ok = status == 200 or (status == 401 and "no key" in name)
    icon = "PASS" if ok else "FAIL"
    if ok:
        passed += 1
    print(f"  [{icon}] {name:45s} {status}  {detail}")
print("=" * 70)
print(f"  RESULT: {passed}/{len(results)} passed")
print("=" * 70)

# Quickstart: decision.action-preflight-forecast

This guide is for external users who want to integrate only the Action Preflight skill.

Terminology used in this document:

- COGIT = capability
- SYLLOG = skill

At implementation level, the runtime and API keep the canonical names `capabilities` and `skills`.

## Scope

Use this quickstart when you want to:

- run only `decision.action-preflight-forecast`
- call it from another stack through HTTP
- avoid full registry authoring flows

Use the freeze/repro guide for research-grade reproducibility:

- `docs/ACTION_PREFLIGHT_FORECAST_EXTERNAL.md`

## Prerequisites

1. Clone both repositories side by side:
   - `agent-skills`
   - `agent-skill-registry`
2. Install runtime dependencies.
3. Ensure registry root is discoverable by the runtime.

PowerShell example:

```powershell
git clone https://github.com/gfernandf/agent-skills.git
git clone https://github.com/gfernandf/agent-skill-registry.git

Set-Location agent-skills
pip install -e ".[all,dev]"

$env:AGENT_SKILLS_REGISTRY_ROOT = "../agent-skill-registry"
python skills.py doctor
```

## Start HTTP API

Local development (no auth):

```powershell
$env:AGENT_SKILLS_AUTH_MODE = "disabled"
python tooling/run_customer_http_api.py --host 127.0.0.1 --port 8080
```

In another terminal, verify health:

```powershell
curl http://127.0.0.1:8080/v1/health
```

## Execute only Action Preflight

Endpoint:

- `POST /v1/skills/decision.action-preflight-forecast/execute`

Minimal request body:

```json
{
  "inputs": {
    "candidate_action": {
      "type": "send_message",
      "channel": "internal_chat",
      "target": "teammate",
      "content": "Confirm the 10:00 meeting"
    },
    "intended_goal": "Confirm an already agreed internal meeting"
  }
}
```

PowerShell call:

```powershell
$body = @'
{
  "inputs": {
    "candidate_action": {
      "type": "send_message",
      "channel": "internal_chat",
      "target": "teammate",
      "content": "Confirm the 10:00 meeting"
    },
    "intended_goal": "Confirm an already agreed internal meeting",
    "context": {
      "contains_sensitive_data": false,
      "external_visibility": "none",
      "reversibility": "high"
    },
    "known_constraints": [
      "Keep professional tone",
      "Do not include sensitive data"
    ],
    "available_evidence": [
      {
        "id": "ev1",
        "content": "Meeting is already present in the internal calendar"
      }
    ],
    "risk_tolerance": "medium"
  }
}
'@

curl -X POST http://127.0.0.1:8080/v1/skills/decision.action-preflight-forecast/execute `
  -H "Content-Type: application/json" `
  -d $body
```

## What to read in the response

Primary output fields:

- `outputs.continuation_decision`
  - includes decision, rationale, confidence_score, risk_level, risk_score
- `outputs.human_readable`
  - human-facing narrative for review/audit
- `outputs.safer_alternatives`
  - alternative actions with safer posture

If your integration needs one stable object, consume `outputs.continuation_decision` first.

## Add API key mode (recommended outside local dev)

```powershell
$env:AGENT_SKILLS_AUTH_MODE = "enforced"
$env:AGENT_SKILLS_API_KEY = "replace-with-your-key"
python tooling/run_customer_http_api.py --host 127.0.0.1 --port 8080
```

Then add header:

- `x-api-key: <your-key>`

## Common integration mistakes

1. Registry path not configured (`AGENT_SKILLS_REGISTRY_ROOT` missing).
2. Calling wrong skill id. Use exact id: `decision.action-preflight-forecast`.
3. Sending invalid JSON shape (inputs must be under `inputs`).
4. Forgetting auth header when auth mode is `enforced`.

## Next references

- Skill contract: `../agent-skill-registry/skills/official/decision/action-preflight-forecast/skill.yaml`
- Neutral API surface: `docs/CONSUMER_FACING_NEUTRAL_API.md`
- External freeze/repro: `docs/ACTION_PREFLIGHT_FORECAST_EXTERNAL.md`
- External validation checklist: `docs/ACTION_PREFLIGHT_FORECAST_EXTERNAL_CHECKLIST.md`

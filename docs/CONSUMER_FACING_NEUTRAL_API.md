# Consumer-Facing Neutral API

Date: 2026-03-11
Status: Implemented v1 gateway baseline
Scope: Single domain contract exposed through HTTP/OpenAPI and MCP bridge adapters

## Purpose

This layer exposes runtime execution to external users without coupling clients to
internal binding protocols.

The same domain operations are now available through:

1. HTTP/OpenAPI adapter
2. MCP tool bridge adapter

Both adapters call the same runtime stack, with gateway-mediated operations for
skill discovery/list/attach and neutral API operations for execution.

## Architecture

Core modules:

1. `runtime/engine_factory.py`
- Shared runtime construction used by CLI and customer-facing adapters.

2. `customer_facing/neutral_api.py`
- Protocol-neutral domain facade.
- Operations: health, describe_skill, execute_skill, execute_capability, async runs, run status/cancel, checkpoints, resume.

3. `gateway/core.py`
- Agent-facing gateway layer.
- Operations: list_skills, discover, attach, diagnostics, reset_diagnostics_metrics.
- Includes attach target validation and diagnostics persistence metadata.

4. `customer_facing/http_openapi_server.py`
- HTTP adapter with v1 routes and OpenAPI spec endpoint.
- Reuses `runtime/openapi_error_contract.py` for deterministic error mapping.
- Optional API-key authentication (`x-api-key`) and in-memory per-client rate limiting.

5. `customer_facing/mcp_tool_bridge.py`
- MCP-oriented tool adapter over the same neutral operations.
- Includes stdio loop for lightweight bridge hosting.

## v1 HTTP Routes

Base version: `/v1`

1. `GET /v1/health`
2. `GET /v1/skills/{skill_id}/describe`
3. `GET /v1/skills/list`
4. `GET /v1/skills/governance`
5. `GET /v1/skills/diagnostics`
6. `POST /v1/skills/discover`
7. `POST /v1/skills/{skill_id}/attach`
8. `POST /v1/skills/{skill_id}/execute`
9. `POST /v1/capabilities/{capability_id}/execute`
10. `POST /v1/capabilities/{capability_id}/explain`
11. `POST /v1/skills/{skill_id}/execute/async`
12. `POST /v1/run_async` (alias) and `POST /run_async` (alias)
13. `GET /v1/runs`
14. `GET /v1/runs/{run_id}`
15. `POST /v1/runs/{run_id}/cancel`
16. `GET /v1/runs/{run_id}/checkpoints`
17. `POST /v1/runs/{run_id}/resume`
18. `POST /v1/runs/{run_id}/approve`
19. `POST /v1/runs/{run_id}/deny`
20. `POST /v1/runs/{run_id}/replay`
21. `POST /v1/runs/{run_id}/fork`
22. `GET /run_status/{run_id}` and `GET /v1/run_status/{run_id}` (legacy aliases)
23. `POST /run_cancel/{run_id}` and `POST /v1/run_cancel/{run_id}` (legacy aliases)
24. `GET /openapi.json`

Async run status model:

- Canonical (`/v1/runs/*`): `pending`, `running`, `waiting_for_human`, `waiting_for_signal`, `replaying`, `completed`, `failed`, `canceled`.
- Legacy aliases project `canceled` to `failed` for compatibility with older clients.

Checkpoint and resume contract:

- `GET /v1/runs/{run_id}/checkpoints` returns checkpoint list + `checkpoint_head`.
- `POST /v1/runs/{run_id}/resume` accepts optional `checkpoint_id`.
- Current slice behavior: resume mode is `checkpoint_resume`; the runtime restores the checkpointed state and continues execution from the remaining steps.
- `POST /v1/runs/{run_id}/approve` accepts optional `approver` and `notes`, then resumes a run that is waiting for human approval.
- `POST /v1/runs/{run_id}/deny` accepts optional `approver` and `notes`, then cancels the run canonically.
- `POST /v1/runs/{run_id}/replay` accepts optional `checkpoint_id`, creates a new replay run, and continues from the restored checkpoint state.
- `POST /v1/runs/{run_id}/fork` accepts optional `checkpoint_id`, creates a new pending run, and preserves source linkage without re-executing.

Security model (configurable):

1. `GET /v1/health` and `GET /openapi.json` can remain unauthenticated.
2. All execution/describe routes can require `x-api-key`.
3. Protected routes can enforce request rate limits with `429` responses.

OpenAPI spec file:

- `docs/specs/consumer_facing_v1_openapi.json`

## MCP Tool Surface

Exposed tools:

1. `runtime.health`
2. `skill.describe`
3. `skill.list`
4. `skill.discover`
5. `skill.diagnostics`
6. `skill.metrics.reset`
7. `skill.attach`
8. `skill.execute`
9. `capability.execute`
10. `capability.explain`
11. `skill.governance.list`

Bridge entrypoint:

- `tooling/run_customer_mcp_bridge.py`

## Error Contract

Both adapters map runtime exceptions through:

- `runtime/openapi_error_contract.py`

Error payload shape:

```json
{
  "error": {
    "code": "string",
    "message": "string",
    "type": "string"
  },
  "trace_id": "string"
}
```

## Runbook

### Run HTTP/OpenAPI server

```bash
python tooling/run_customer_http_api.py --host 127.0.0.1 --port 8080
```

Run with API key + rate limit:

```bash
python tooling/run_customer_http_api.py --host 127.0.0.1 --port 8080 --api-key local-dev-key --rate-limit-requests 20 --rate-limit-window-seconds 60
```

### Run MCP bridge (stdio)

```bash
python tooling/run_customer_mcp_bridge.py
```

Example stdio request line:

```json
{"id":"1","method":"tools/call","params":{"name":"skill.execute","arguments":{"skill_id":"agent.plan-from-objective","inputs":{"objective":"Build a plan"}}}}
```

Example attach request line (generic sidecar attach):

```json
{"id":"2","method":"tools/call","params":{"name":"skill.attach","arguments":{"skill_id":"agent.trace","target_type":"output","target_ref":"<existing-trace-or-output-ref>","include_trace":true,"inputs":{"goal":"Trace current orchestration","events":[],"trace_state":{},"trace_session_id":"session-1"}}}}
```

### Verify both adapters

```bash
python tooling/verify_customer_facing_neutral.py
```

### Verify HTTP controls (auth + throttling)

```bash
python tooling/verify_customer_http_controls.py
```

### Verify HTTP/MCP parity snapshot

```bash
python tooling/verify_customer_facing_parity_snapshot.py
```

## Design Invariants

1. Consumer-facing contract is protocol-neutral and stable.
2. Internal provider protocols (pythoncall/openapi/mcp/openrpc) remain behind binding resolution.
3. Adding or changing internal protocols must not require external API contract changes.
4. Trace propagation uses `x-trace-id` header or `trace_id` body field.
5. Skill ranking is heuristic; product agents should apply selection policy and not rely exclusively on top-1 score.

## Product Agent Orchestration Pattern

Recommended policy for product-facing agents:

1. Discover candidates for the primary user intent.
2. Execute primary skill.
3. Attach optional sidecar skills (monitoring/control/reporting) when requested by user policy.
4. Return both business output and execution trace/control summary.

This pattern treats sidecar skills as a normal classified skill category (`role=sidecar`,
`invocation=attach|both`) and avoids hard-coded behavior for any single skill id.

## Next Steps

1. Replace in-memory rate limiting with distributed/shared limiter for multi-instance deployment.
2. Replace static API key with pluggable authn/authz provider.
3. Replace stdio MCP bridge with full MCP server transport integration.
4. Extend parity snapshots across more capabilities and representative error cases.

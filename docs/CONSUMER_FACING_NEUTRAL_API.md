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
- Operations: health, describe_skill, execute_skill, execute_capability.

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
4. `GET /v1/skills/diagnostics`
5. `POST /v1/skills/discover`
6. `POST /v1/skills/{skill_id}/attach`
7. `POST /v1/skills/{skill_id}/execute`
8. `POST /v1/capabilities/{capability_id}/execute`
9. `GET /openapi.json`

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

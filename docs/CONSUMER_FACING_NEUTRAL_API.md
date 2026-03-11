# Consumer-Facing Neutral API

Date: 2026-03-11
Status: Implemented v1 baseline
Scope: Single domain contract exposed through HTTP/OpenAPI and MCP bridge adapters

## Purpose

This layer exposes runtime execution to external users without coupling clients to
internal binding protocols.

The same domain operations are now available through:

1. HTTP/OpenAPI adapter
2. MCP tool bridge adapter

Both adapters call the same neutral runtime facade.

## Architecture

Core modules:

1. `runtime/engine_factory.py`
- Shared runtime construction used by CLI and customer-facing adapters.

2. `customer_facing/neutral_api.py`
- Protocol-neutral domain facade.
- Operations: health, describe_skill, execute_skill, execute_capability.

3. `customer_facing/http_openapi_server.py`
- HTTP adapter with v1 routes and OpenAPI spec endpoint.
- Reuses `runtime/openapi_error_contract.py` for deterministic error mapping.

4. `customer_facing/mcp_tool_bridge.py`
- MCP-oriented tool adapter over the same neutral operations.
- Includes stdio loop for lightweight bridge hosting.

## v1 HTTP Routes

Base version: `/v1`

1. `GET /v1/health`
2. `GET /v1/skills/{skill_id}/describe`
3. `POST /v1/skills/{skill_id}/execute`
4. `POST /v1/capabilities/{capability_id}/execute`
5. `GET /openapi.json`

OpenAPI spec file:

- `docs/specs/consumer_facing_v1_openapi.json`

## MCP Tool Surface

Exposed tools:

1. `runtime.health`
2. `skill.describe`
3. `skill.execute`
4. `capability.execute`

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

### Run MCP bridge (stdio)

```bash
python tooling/run_customer_mcp_bridge.py
```

Example stdio request line:

```json
{"id":"1","method":"tools/call","params":{"name":"skill.execute","arguments":{"skill_id":"agent.plan-from-objective","inputs":{"objective":"Build a plan"}}}}
```

### Verify both adapters

```bash
python tooling/verify_customer_facing_neutral.py
```

## Design Invariants

1. Consumer-facing contract is protocol-neutral and stable.
2. Internal provider protocols (pythoncall/openapi/mcp/openrpc) remain behind binding resolution.
3. Adding or changing internal protocols must not require external API contract changes.
4. Trace propagation uses `x-trace-id` header or `trace_id` body field.

## Next Steps

1. Add authentication and authorization middleware/policy checks.
2. Add rate limiting and request-size guardrails in HTTP adapter.
3. Replace stdio MCP bridge with full MCP server transport integration.
4. Add parity tests ensuring equivalent logical output across HTTP and MCP adapters.

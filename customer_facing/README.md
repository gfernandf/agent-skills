# customer_facing/ — HTTP server implementations

This directory contains the server entry points that expose agent-skills over HTTP.

| File | Purpose | When to use |
|------|---------|-------------|
| `neutral_api.py` | `NeutralRuntimeAPI` — framework-agnostic API class | Base class for all servers; extend this if building a custom server |
| `fastapi_server.py` | FastAPI-based async server | Production deployments needing async, OpenAPI docs, middleware |
| `http_openapi_server.py` | Stdlib `http.server`-based server | Zero-dependency option; used by `agent-skills serve` CLI |
| `mcp_tool_bridge.py` | MCP→HTTP bridge | Proxies MCP tool calls to the HTTP server |

## Quick start

```bash
# Stdlib server (no extra dependencies)
agent-skills serve

# FastAPI server (requires uvicorn)
uvicorn customer_facing.fastapi_server:app --host 0.0.0.0 --port 8080
```

## Extending

To add custom middleware or endpoints, subclass `NeutralRuntimeAPI`:

```python
from customer_facing.neutral_api import NeutralRuntimeAPI

class MyAPI(NeutralRuntimeAPI):
    def custom_endpoint(self, request):
        ...
```

## Async execution contract

Both HTTP servers support async start-and-poll semantics.

- Start async run (skill-specific): `POST /v1/skills/{skill_id}/execute/async`
- Start async run (generic alias): `POST /run_async` or `POST /v1/run_async`
    - Body: `{ "skill_id": "...", "inputs": { ... } }`
    - Returns immediately with `run_id` and initial status.
- Poll run status: `GET /v1/runs/{run_id}`
- Poll run status (alias): `GET /run_status/{run_id}` or `GET /v1/run_status/{run_id}`
- List recent runs: `GET /v1/runs?limit=100&offset=0&status=running|completed|failed`
- Cancel run: `POST /v1/runs/{run_id}/cancel`
- Cancel run (alias): `POST /run_cancel/{run_id}` or `POST /v1/run_cancel/{run_id}`
- List run checkpoints: `GET /v1/runs/{run_id}/checkpoints`
- Resume run from latest checkpoint: `POST /v1/runs/{run_id}/resume`
    - Body (optional): `{ "checkpoint_id": "<checkpoint-id>" }`
- Approve waiting run: `POST /v1/runs/{run_id}/approve`
- Deny waiting run: `POST /v1/runs/{run_id}/deny`
- Replay run from checkpoint: `POST /v1/runs/{run_id}/replay`
    - Body (optional): `{ "checkpoint_id": "<checkpoint-id>" }`

Run states:

- Canonical (`/v1/runs/*`): `pending`, `running`, `waiting_for_human`, `replaying`, `completed`, `failed`, `canceled`
- Legacy aliases (`/run_status/*`, `/run_cancel/*`): `canceled` is projected as `failed` for backward compatibility

Notes:

- The HTTP request timeout does not cancel a run once accepted.
- Final async result payload preserves the same output/meta diagnostics shape as sync execution.
- `resume` now performs checkpoint-backed continuation and only re-executes the remaining steps after the restored checkpoint state.
- `replay` creates a new replay run linked to the source run and checkpoint, then re-executes from the restored checkpoint state.

## Webhook callback (optional)

You can subscribe callback URLs and receive async completion events:

- Register: `POST /v1/webhooks`
- List: `GET /v1/webhooks`
- Delete: `DELETE /v1/webhooks/{id}`

Run completion events emitted:

- `run.completed`
- `run.failed`
```

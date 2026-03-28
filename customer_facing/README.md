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

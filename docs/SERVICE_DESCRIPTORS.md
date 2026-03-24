# Service Descriptors

> How external HTTP services are declared and resolved at runtime.

---

## What is a service descriptor?

A service descriptor is a YAML file that tells the runtime how to reach an
external HTTP API. It lives under `services/official/` and is referenced by
bindings that use the `openapi` protocol.

---

## File format

```yaml
id: text_openai_chat
type: openapi
base_url: https://api.openai.com/v1
auth:
  type: bearer
  token: ${OPENAI_API_KEY}
headers:
  Content-Type: application/json
```

### Required fields

| Field | Type | Description |
|---|---|---|
| `id` | string | Unique service identifier, referenced by bindings |
| `type` | string | Protocol type: `openapi`, `mcp`, `openrpc` |
| `base_url` | string | Base URL for the API (no trailing slash) |

### Optional fields

| Field | Type | Description |
|---|---|---|
| `auth` | object | Authentication configuration |
| `auth.type` | string | `bearer`, `api_key`, `basic` |
| `auth.token` | string | Token value or env var placeholder |
| `auth.header` | string | Custom header name (for `api_key` type) |
| `headers` | object | Additional HTTP headers |
| `timeout` | integer | Request timeout in seconds |

---

## Environment variable placeholders

Use `${ENV_VAR}` syntax for secrets:

```yaml
auth:
  type: bearer
  token: ${OPENAI_API_KEY}
```

The runtime resolves `${OPENAI_API_KEY}` from the process environment at
invocation time. If the variable is not set, the request will fail with a
clear error referencing the missing variable.

---

## How bindings reference services

A binding with `protocol: openapi` points to a service descriptor by its `id`:

```yaml
# bindings/official/text.content.summarize/openapi_text_summarize_openai_chat.yaml
id: openapi_text_summarize_openai_chat
capability: text.content.summarize
service: text_openai_chat           # ← matches service descriptor id
protocol: openapi
operation: chat/completions         # ← HTTP path appended to base_url
```

At runtime, the invoker constructs:
`POST https://api.openai.com/v1/chat/completions`

---

## SSRF protection

The `openapi_invoker` enforces URL safety:

- Only `http` and `https` schemes are allowed.
- Requests to private/link-local IPs and cloud metadata endpoints
  (`169.254.169.254`) are blocked.
- The final resolved URL is validated, not just the configured one.

See `docs/SECURITY.md` for details.

---

## Python baseline services (no descriptor needed)

Bindings with `protocol: pythoncall` don't need a service descriptor. The
`service` field is the Python module name under `official_services/`:

```yaml
service: text_baseline    # → official_services/text_baseline.py
protocol: pythoncall
operation: summarize_text # → text_baseline.summarize_text()
```

---

## Existing service descriptors

| File | ID | API |
|---|---|---|
| `services/official/text_openai_chat.yaml` | `text_openai_chat` | OpenAI Chat Completions |
| `services/official/text_mcp_inprocess.yaml` | `text_mcp_inprocess` | In-process MCP (text) |
| `services/official/data_mcp_inprocess.yaml` | `data_mcp_inprocess` | In-process MCP (data) |
| `services/official/web_mcp_inprocess.yaml` | `web_mcp_inprocess` | In-process MCP (web) |

---

## Adding a new service descriptor

1. Create `services/official/<id>.yaml` with the fields above.
2. Set `${ENV_VAR}` placeholders for any secrets.
3. Create a binding YAML that references the service `id`.
4. Document the required environment variable in `.env.example`.
5. Test: `python test_capabilities_batch.py` (with the env var set).

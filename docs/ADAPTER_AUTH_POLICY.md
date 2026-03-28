# Adapter Authentication & Secret Handling Policy

> How credentials and secrets flow through the MCP server, LLM adapters,
> and HTTP API — and what each layer is responsible for.

## Principle: Secrets Stay at the Edge

Secrets (API keys, tokens, credentials) are never stored inside capability
contracts, skill YAML, or binding definitions. They live in the environment
and are resolved at execution time by the binding layer.

```
┌──────────────────────────────────────────────────────────────────┐
│  Environment (env vars, config files, secret managers)           │
│  OPENAI_API_KEY, AGENT_SKILLS_JWT_SECRET, etc.                  │
└──────────────────────┬───────────────────────────────────────────┘
                       │ resolved at runtime
┌──────────────────────▼───────────────────────────────────────────┐
│  Binding Layer (ProtocolRouter → Invoker)                        │
│  - openapi_invoker reads API keys from env                       │
│  - mcp_invoker reads server config from env                      │
│  - pythoncall_invoker has no secrets                              │
└──────────────────────────────────────────────────────────────────┘
```

## Per-Surface Auth Model

### HTTP API (`agent-skills serve`)

| Mechanism | Header | Implementation |
|-----------|--------|---------------|
| API Key | `X-API-Key` | `ApiKeyStore` (SHA-256 hashed) |
| JWT HS256 | `Authorization: Bearer <token>` | `JWTVerifier` in `runtime/auth.py` |
| Anonymous | — | Opt-in via `allow_anonymous`, gets `reader` role |

**Activation**: Set `AGENT_SKILLS_RBAC=1`. Without it, legacy flat API key
check applies (backward-compatible).

See [AUTH.md](AUTH.md) for full configuration.

### MCP Server (`python -m official_mcp_servers`)

The MCP server runs as a **local subprocess** managed by the MCP host
(Claude Desktop, VS Code, etc.). Authentication follows the MCP transport
model:

| Transport | Auth Model |
|-----------|-----------|
| **stdio** | Implicit trust — the host process owns the subprocess. No additional auth needed. |
| **SSE** | Network-exposed — use `AGENT_SKILLS_MCP_API_KEY` env var to require a key in the `Authorization` header. |

**Environment variables for MCP:**

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENT_SKILLS_MCP_API_KEY` | *(none)* | When set, SSE transport requires this key |
| `AGENT_SKILLS_MCP_TRUST_LEVEL` | `standard` | Maximum trust level for capability execution |

### Native LLM Adapters (`as_anthropic_tools`, etc.)

The LLM adapters run **in-process** in the caller's Python runtime. They
inherit the caller's environment and have no independent auth layer.

| Concern | Policy |
|---------|--------|
| **Adapter auth** | None — the caller already has code access |
| **Upstream API keys** | Resolved by the binding layer from env vars |
| **Secret leakage** | `execute_*_tool_call()` returns sanitized JSON; errors never contain credentials |

### Framework Adapters (LangChain, CrewAI, etc.)

Same model as native LLM adapters — they create tool wrappers that call
`execute_capability()` internally. No separate auth.

## Secret Resolution Flow

When a binding needs an API key (e.g., OpenAI):

```
1. Skill YAML → step references capability "text.content.summarize"
2. Binding resolver finds best binding (e.g., openapi_text_summarize)
3. Binding metadata declares: auth: { type: "bearer", env: "OPENAI_API_KEY" }
4. openapi_invoker reads os.environ["OPENAI_API_KEY"] at call time
5. Key is placed in Authorization header for the upstream request
6. Key is NEVER logged — header redaction is active in openapi_invoker
```

## Credential Redaction

All surfaces sanitize credentials before logging or returning errors:

- **Audit system** (`runtime/audit.py`): Recursive redaction of keys containing
  `password`, `token`, `secret`, `key`, `authorization`, `credential`.
- **OpenAPI invoker**: Header redaction for `Authorization`, `X-API-Key`,
  `Cookie`, and related headers.
- **Error responses**: `sanitize_error_message()` truncates and strips
  multi-line content. No exception causes are exposed to clients.

## Adding Auth to a New Surface

When creating a new adapter or transport:

1. **Determine trust model**: Is it local (implicit trust) or network (explicit auth)?
2. **Reuse `AuthMiddleware`** for network surfaces: it handles API key + JWT + anonymous.
3. **Never store secrets in code**: Use env vars or the plugin system (`agent_skills.auth` entry point).
4. **Always sanitize errors**: Use `sanitize_error_message()` from `openapi_error_contract.py`.
5. **Log auth events**: Use `log_event("auth.*")` for auditable auth decisions.

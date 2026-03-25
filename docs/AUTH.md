# Authentication & RBAC

agent-skills provides a pluggable authentication and role-based access
control (RBAC) system for the HTTP API.

## Role hierarchy

Four roles are defined, ordered by ascending privilege:

| Role | Can access |
|---|---|
| `reader` | Health, describe, list, governance, discover |
| `executor` | Reader + execute (sync, stream, async), attach, capabilities |
| `operator` | Executor + webhooks, runs management |
| `admin` | Operator + all endpoints (including unknown future routes) |

Higher roles inherit all permissions from lower roles.

## Enabling RBAC

Set the environment variable `AGENT_SKILLS_RBAC=1` before starting
the server:

```bash
export AGENT_SKILLS_RBAC=1
agent-skills serve --api-key my-key --port 8080
```

When RBAC is enabled, the configured `--api-key` is registered as an
`admin` key automatically. Without RBAC enabled, the legacy flat
API-key check is used (backward-compatible).

## Authentication methods

### API key (X-API-Key header)

```http
POST /v1/skills/my-skill/execute
X-API-Key: my-admin-key
```

Keys are stored as SHA-256 hashes — the raw key is never kept in memory.

### Bearer token (JWT HS256)

Set `AGENT_SKILLS_JWT_SECRET` to enable JWT authentication:

```bash
export AGENT_SKILLS_JWT_SECRET=my-256-bit-secret
export AGENT_SKILLS_RBAC=1
agent-skills serve
```

Tokens must include a `sub` claim. The `role` claim maps to the RBAC
hierarchy. If no `role` claim is present, `executor` is used as default.

```http
POST /v1/skills/my-skill/execute
Authorization: Bearer eyJhbGciOiJIUzI1NiIs...
```

**Token claims:**

| Claim | Required | Description |
|---|---|---|
| `sub` | Yes | Subject identifier |
| `role` | No | One of: reader, executor, operator, admin |
| `exp` | No | Expiry timestamp (UNIX epoch). Rejected if expired. |

### Anonymous access

When no API key or JWT secret is configured and RBAC is enabled,
anonymous requests are assigned the `reader` role. Disable anonymous
access by setting at least one API key.

## Route → role mapping

| Method | Path pattern | Required role |
|---|---|---|
| GET | `/v1/health` | reader |
| GET | `/openapi.json` | reader |
| GET | `/v1/skills/list` | reader |
| GET | `/v1/skills/governance` | reader |
| GET | `/v1/skills/diagnostics` | reader |
| GET | `/v1/skills/{id}/describe` | reader |
| POST | `/v1/skills/discover` | reader |
| POST | `/v1/skills/{id}/execute` | executor |
| POST | `/v1/skills/{id}/execute/stream` | executor |
| POST | `/v1/skills/{id}/execute/async` | executor |
| POST | `/v1/skills/{id}/attach` | executor |
| POST | `/v1/capabilities/{id}/execute` | executor |
| GET | `/v1/runs` | operator |
| POST/GET | `/v1/webhooks` | operator |
| DELETE | `/v1/webhooks/{id}` | operator |
| * | Unknown routes | admin |

## Programmatic usage

```python
from runtime.auth import AuthMiddleware, ApiKeyStore, JWTVerifier

store = ApiKeyStore()
store.register("key-abc", subject="alice", role="admin")
store.register("key-xyz", subject="bob", role="executor")

jwt = JWTVerifier("my-secret", default_role="executor")

middleware = AuthMiddleware(
    api_key_store=store,
    token_verifier=jwt,
    allow_anonymous=False,
)

# In your request handler:
identity = middleware.authenticate({"x-api-key": "key-abc"})
if middleware.authorize(identity, "POST", "/v1/skills/s1/execute"):
    # proceed
    ...
```

## Plugin extension

Third-party auth backends can be registered via entry points:

```toml
[project.entry-points."agent_skills.auth"]
my_oauth = "my_package.auth:OAuthBackend"
```

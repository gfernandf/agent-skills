# Environment Variables Reference

All environment variables use the `AGENT_SKILLS_` prefix.

## Core Paths

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENT_SKILLS_REGISTRY_ROOT` | `../agent-skill-registry` (sibling dir) | Path to the registry repo (capabilities, skills, vocabulary) |
| `AGENT_SKILLS_RUNTIME_ROOT` | Project root | Path to agent-skills runtime root |
| `AGENT_SKILLS_HOST_ROOT` | Same as runtime root | Path to the host root (local overrides, `.agent-skills/` dir) |

## Server Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENT_SKILLS_HOST` | `127.0.0.1` | Bind address for the HTTP server |
| `AGENT_SKILLS_PORT` | `8080` | Port for the HTTP server |
| `AGENT_SKILLS_CORS_ORIGINS` | _(empty — CORS disabled)_ | Comma-separated allowed origins (e.g. `http://localhost:3000,https://app.example.com`) |
| `AGENT_SKILLS_DRAIN_SECONDS` | `5` | Graceful shutdown drain period (seconds) |
| `AGENT_SKILLS_ASYNC_WORKERS` | `4` | Number of async execution workers for `/execute/async` |
| `AGENT_SKILLS_MAX_RUNS` | `100` | Maximum stored runs in the in-memory RunStore |

## Authentication

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENT_SKILLS_AUTH_MODE` | `enforced` | Auth enforcement: `enforced` (reject unauthenticated — **default since v0.2.0**), `permissive` (allow anonymous as reader), `disabled` |
| `AGENT_SKILLS_API_KEY` | _(none)_ | API key for `X-API-Key` header authentication |
| `AGENT_SKILLS_RBAC` | _(deprecated)_ | **Deprecated** — use `AGENT_SKILLS_AUTH_MODE=enforced` instead. Setting `1`/`true`/`yes` enables enforced mode. |
| `AGENT_SKILLS_TRUSTED_PROXIES` | _(empty)_ | Comma-separated trusted proxy CIDRs for `X-Forwarded-For` parsing |

## Webhooks

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENT_SKILLS_WEBHOOKS_REQUIRE_SECRET` | _(empty)_ | When set to `1`/`true`, webhook registration requires an HMAC secret |

## Execution Safety

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENT_SKILLS_PYTHONCALL_ALLOWED_MODULES` | _(empty — all allowed)_ | Comma-separated allowlist of Python modules for PythonCall bindings |
| `AGENT_SKILLS_PYTHONCALL_TIMEOUT` | `30` | Timeout in seconds for PythonCall binding execution |

## Scaffolder

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENT_SKILLS_SCAFFOLDER_MODE` | `binding-first` | Scaffolding mode: `binding-first` or `contract-first` |

# Security Hardening Reference

> Covers OWASP-relevant protections implemented in agent-skills v0.1.0.

---

## 1. Server-Side Request Forgery (SSRF) — `runtime/openapi_invoker.py`

Every outbound HTTP call goes through `OpenAPIInvoker._validate_url()` which
enforces:

| Check | Detail |
|-------|--------|
| **Scheme allow-list** | Only `http` and `https` are accepted. |
| **Cloud metadata blocklist** | Requests to `169.254.169.254`, `100.100.100.200`, `fd00:ec2::254` are **always** blocked. |
| **Private-network guard** | By default, resolved IPs that are `is_private`, `is_loopback`, `is_link_local`, or `is_reserved` are blocked. Set `allow_private_networks=True` in the invoker to allow local-network services. |
| **DNS resolution** | Hostname is resolved with `socket.getaddrinfo` before any connection; all resolved addresses are checked. |

### Configuration

```python
OpenAPIInvoker(allow_private_networks=False)   # default — strict
OpenAPIInvoker(allow_private_networks=True)     # for local dev / on-prem
```

---

## 2. Local File Inclusion (LFI) — `official_services/fs_baseline.py`

The `fs.file.read` capability validates every path before access:

1. `os.path.realpath(path)` resolves symlinks and `..` traversals.
2. `os.path.commonpath([root, resolved])` verifies the resolved path shares
   the allowed root prefix.
3. If the check fails, `ValueError("Access denied")` is raised.

### Configuration

| Env var | Default | Purpose |
|---------|---------|---------|
| `AGENT_SKILLS_FS_ROOT` | `os.getcwd()` | Root directory for fs operations. Nothing outside this tree is accessible. |

---

## 3. Credential Handling

### 3a. Header redaction — `runtime/openapi_invoker.py`

When logging or tracing HTTP calls, headers matching these names are replaced
with `***`:

```
authorization, x-api-key, api-key, x-secret, cookie
```

### 3b. Audit record sanitization — `runtime/audit.py`

All audit records pass through a recursive `_sanitize()` function that:

- Replaces values whose key contains any of: `password`, `secret`, `token`,
  `apikey`, `api_key`, `authorization`, `auth`, `cookie`, `key`, `private`,
  `credential`, `session` → with `[REDACTED]`.
- Truncates large strings and collections to prevent log bloat.

### 3c. Environment variable injection — `runtime/openapi_invoker.py`

Credentials are injected at call time via `${ENV_VAR}` placeholders in service
headers (e.g., `Authorization: Bearer ${OPENAI_API_KEY}`). Credentials never
appear in YAML files or audit logs.

---

## 4. Request Body Limits — `customer_facing/http_openapi_server.py`

| Parameter | Default | Purpose |
|-----------|---------|---------|
| `max_request_body_bytes` | 2 MB (2 × 1024 × 1024) | Reject oversized payloads before JSON parsing. |

The `Content-Length` header is checked before reading the body. If absent or
zero, an empty dict is returned.

---

## 5. Rate Limiting — `customer_facing/http_openapi_server.py`

Per-client IP rate limiting with sliding-window counters:

| Parameter | Default | Env var |
|-----------|---------|---------|
| `rate_limit_requests` | 60 | `AGENT_SKILLS_RATE_LIMIT_REQUESTS` |
| `rate_limit_window_seconds` | 60 | `AGENT_SKILLS_RATE_LIMIT_WINDOW` |

- Returns HTTP `429` with `RateLimitError` when exceeded.
- Stale client entries are garbage-collected on every request to prevent
  unbounded memory growth.
- Paths listed in `unauthenticated_paths` (e.g., health check) are exempt.

---

## 6. Input Validation

- JSON body must parse as a `dict` (not a list or scalar).
- Path parameters and capability IDs are validated against the registry before
  execution.
- Template variables undergo strict substitution (no code evaluation).

---

## 7. What is NOT yet implemented

| Gap | Mitigation |
|-----|-----------|
| CORS headers | Server binds to `127.0.0.1` by default; add an API gateway for cross-origin deployments. |
| TLS termination | Use a reverse proxy (nginx, Caddy) for HTTPS. |
| JWT / OAuth | Currently uses `x-api-key` header; integrate your auth layer for multi-tenant. |
| Content Security Policy | Not applicable — server is API-only, no HTML rendering. |

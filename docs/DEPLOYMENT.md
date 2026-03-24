# Deployment Guide

> From development install to a hardened production instance.

---

## Prerequisites

- Python ≥ 3.11
- `agent-skill-registry` cloned alongside `agent-skills` (sibling directories)

---

## 1. Development install

```bash
cd agent-skills
python -m pip install -e ".[all]"
```

Copy and fill `.env.example`:

```bash
cp .env.example .env
# Edit .env — at minimum set OPENAI_API_KEY for LLM-backed capabilities
```

Verify:

```bash
agent-skills doctor
```

---

## 2. Production install

### 2a. Locked dependencies

```bash
pip install ".[all]" --no-deps   # after resolving versions in a lockfile
```

Or use a container:

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir ".[all]"
CMD ["agent-skills", "serve"]
```

### 2b. Environment variables

| Variable | Required | Default | Purpose |
|----------|:--------:|---------|---------|
| `OPENAI_API_KEY` | For LLM caps | — | OpenAI API key |
| `AGENT_SKILLS_FS_ROOT` | No | `cwd` | Sandbox root for `fs.file.read` |
| `AGENT_SKILLS_AUDIT_DEFAULT_MODE` | No | `standard` | `off` / `standard` / `full` |
| `AGENT_SKILLS_MAX_WORKERS` | No | CPU+4 | Concurrent step threads |
| `AGENT_SKILLS_API_KEY` | For HTTP | — | Server API key for `x-api-key` auth |
| `AGENT_SKILLS_HOST` | No | `127.0.0.1` | Bind address |
| `AGENT_SKILLS_PORT` | No | `8080` | Bind port |
| `AGENT_SKILLS_DEBUG` | No | unset | Enable debug logging |

### 2c. Reverse proxy (recommended)

The built-in HTTP server is single-process. For production:

```
Client  →  nginx / Caddy (TLS, CORS, auth)  →  agent-skills serve (:8080)
```

Nginx example:

```nginx
server {
    listen 443 ssl;
    server_name skills.example.com;

    ssl_certificate     /etc/ssl/certs/skills.pem;
    ssl_certificate_key /etc/ssl/private/skills.key;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;

        # Body limit (should match AGENT_SKILLS max_request_body_bytes)
        client_max_body_size 2m;
    }
}
```

---

## 3. Scaling

### Single instance

Each agent-skills instance is stateless (aside from the audit JSONL file).
Scale horizontally by running multiple instances behind a load balancer.

### Audit at scale

- With multiple instances, each writes to its own audit file.
- Use `AGENT_SKILLS_AUDIT_DEFAULT_MODE=off` to disable audit when you have
  external observability (e.g., OpenTelemetry).
- Periodically purge old records: `agent-skills purge --older-than-days 30`.

### Worker tuning

```bash
# For IO-heavy workloads (many OpenAPI calls)
export AGENT_SKILLS_MAX_WORKERS=16

# For CPU-heavy workloads (large text baselines)
export AGENT_SKILLS_MAX_WORKERS=4
```

---

## 4. Health check

```bash
curl http://127.0.0.1:8080/health
# → {"status": "ok"}
```

---

## 5. Security checklist

Before exposing to a network:

- [ ] Set `AGENT_SKILLS_API_KEY` to a strong random value.
- [ ] Set `AGENT_SKILLS_FS_ROOT` to a dedicated read-only directory.
- [ ] Put a TLS-terminating reverse proxy in front.
- [ ] Review `docs/SECURITY.md` for SSRF, LFI, rate limiting details.
- [ ] Set `AGENT_SKILLS_AUDIT_DEFAULT_MODE=full` for regulated environments.
- [ ] Restrict `allow_private_networks` to `False` (default) unless on-prem.

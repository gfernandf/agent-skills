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

---

## 4. CLI `serve` Command

Start the HTTP API server directly:

```bash
agent-skills serve
```

| Flag              | Env Variable                | Default     | Description                      |
|-------------------|-----------------------------|-------------|----------------------------------|
| `--host`          | `AGENT_SKILLS_HOST`         | `127.0.0.1` | Bind address                     |
| `--port`          | `AGENT_SKILLS_PORT`         | `8080`      | Bind port                        |
| `--api-key`       | `AGENT_SKILLS_API_KEY`      | *(none)*    | API key for `x-api-key` auth     |
| `--cors-origins`  | `AGENT_SKILLS_CORS_ORIGINS` | *(none)*    | Comma-separated allowed origins  |

Example:

```bash
agent-skills serve --host 0.0.0.0 --port 9090 --api-key my-secret
```

---

## 5. Docker

### Build

```bash
docker build -t agent-skills .
```

### Run

```bash
docker run -p 8080:8080 \
  -e AGENT_SKILLS_API_KEY=my-secret \
  -e OPENAI_API_KEY=sk-... \
  agent-skills
```

### docker-compose

Create a `.env` file in the project root:

```dotenv
AGENT_SKILLS_API_KEY=my-secret
OPENAI_API_KEY=sk-...
```

Then:

```bash
docker compose up -d
```

The compose file exposes port `${AGENT_SKILLS_PORT:-8080}`, mounts `./bindings` read-write, and creates a `skills-data` named volume for artifacts.  A health check hits `GET /v1/health` every 30 s.

### Environment Variables Reference

| Variable                       | Default    | Purpose                          |
|--------------------------------|------------|----------------------------------|
| `AGENT_SKILLS_HOST`            | `0.0.0.0`  | Bind address inside container   |
| `AGENT_SKILLS_PORT`            | `8080`     | Server port                      |
| `AGENT_SKILLS_API_KEY`         |            | Auth for protected routes        |
| `AGENT_SKILLS_CORS_ORIGINS`    |            | Comma-separated origins          |
| `AGENT_SKILLS_MAX_WORKERS`     | CPU+4      | DAG scheduler thread pool        |
| `AGENT_SKILLS_ASYNC_WORKERS`   | `4`        | Async execution thread pool      |
| `AGENT_SKILLS_MAX_RUNS`        | `100`      | Max tracked async runs           |
| `OPENAI_API_KEY`               |            | For LLM-backed skills            |
| `OTEL_EXPORTER_OTLP_ENDPOINT` |            | OTel collector endpoint          |
| `OTEL_SERVICE_NAME`            | `agent-skills` | OTel service name           |

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

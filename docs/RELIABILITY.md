# Reliability Features

> Retry, backoff, timeouts, concurrency, and audit durability.

---

## 1. HTTP Retry with Exponential Backoff

**File:** `runtime/openapi_invoker.py`

When an OpenAPI binding receives a transient HTTP error, the invoker retries
automatically.

### Transient status codes

```
429  Too Many Requests
502  Bad Gateway
503  Service Unavailable
504  Gateway Timeout
```

### Default parameters

| Parameter | Default | Override |
|-----------|---------|---------|
| Max retries | 3 | Binding YAML `retry_count` or service descriptor `retry_count` |
| Backoff base | 1.0 s | Binding YAML `retry_backoff_base` |
| Backoff factor | 2.0 | Binding YAML `retry_backoff_factor` |
| Retry-After cap | 60 s | Hardcoded (`_MAX_RETRY_AFTER_SECONDS`) |

### Backoff schedule (defaults)

| Attempt | Delay |
|---------|-------|
| 1st retry | 1 s |
| 2nd retry | 2 s |
| 3rd retry | 4 s |

### Retry-After header

If the server responds with a `Retry-After` header, the invoker honors it
(capped at 60 s). If the header is absent or unparseable, exponential backoff
is used.

### Per-binding override

```yaml
# In a binding YAML
metadata:
  retry_count: 5
  retry_backoff_base: 0.5
  retry_backoff_factor: 3.0
```

---

## 2. Per-Step Timeout

**File:** `runtime/execution_engine.py`

Each skill step runs in a `ThreadPoolExecutor(max_workers=1)` with a timeout.
If the step exceeds the timeout, `StepTimeoutError` is raised and the skill
execution is aborted.

### Timeout resolution order

1. `step.config.timeout_seconds` (per-step in skill YAML)
2. `context.options.step_timeout_seconds` (per-invocation option)
3. `_DEFAULT_STEP_TIMEOUT_SECONDS` = **60 s**

### Configuration in skill YAML

```yaml
steps:
  - id: slow_step
    capability: web.page.fetch
    config:
      timeout_seconds: 120   # override to 2 minutes
```

### Configuration at invocation time

```python
engine.execute(request, options={"step_timeout_seconds": 30})
```

---

## 3. Worker Pool Sizing

**File:** `runtime/scheduler.py`

The DAG scheduler runs steps using a thread pool. Pool size is configurable
via environment variable:

| Env var | Default | Purpose |
|---------|---------|---------|
| `AGENT_SKILLS_MAX_WORKERS` | `min(32, os.cpu_count() + 4)` | Max concurrent step threads |

```bash
export AGENT_SKILLS_MAX_WORKERS=8
```

Steps that fail raise a structured `StepResult` with error details instead of
crashing the entire skill execution.

---

## 4. Audit Durability

**File:** `runtime/audit.py`

### File locking

All audit writes acquire an exclusive advisory lock:

- **Windows:** `msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)`
- **Linux/macOS:** `fcntl.flock(f.fileno(), fcntl.LOCK_EX)`

This prevents corruption from concurrent write access (e.g., multiple CLI
invocations or the HTTP server processing parallel requests).

### Atomic purge

The `purge()` operation uses a safe read-filter-replace cycle:

1. Lock the audit file.
2. Read all lines, filter out matching records.
3. Write kept records to a temp file (`tempfile.mkstemp`).
4. `os.replace(tmp_path, audit_file)` — atomic on most OS/filesystem combos.
5. Clean up temp file on failure.
6. Unlock.

---

## 5. Graceful Degradation

- **Python baselines**: Every capability has a local Python fallback that works
  without network access. Quality is degraded but execution proceeds.
- **Binding fallback**: OpenAI bindings declare `fallback_binding_id` pointing
  to the Python baseline; the runtime can fall through on API failure.
- **Audit modes**: `off | standard | full` — operators can disable audit
  overhead entirely for latency-critical deployments.

# SLO / SLI — Service Level Objectives & Indicators

> Per-capability latency and error budgets for agent-skills.

## Definitions

| Term | Meaning |
|------|---------|
| **SLI** (Service Level Indicator) | A measurable metric — e.g., p95 latency, error rate |
| **SLO** (Service Level Objective) | A target for an SLI — e.g., p95 < 200 ms |
| **Error Budget** | Allowed failure rate — e.g., 0.1% of executions may fail |

## Default SLOs

These defaults apply to all capabilities unless overridden per-domain.

| SLI | Target | Measurement |
|-----|--------|-------------|
| **p50 latency** | < 100 ms | Per-capability `execute()` wall clock |
| **p95 latency** | < 500 ms | Per-capability `execute()` wall clock |
| **p99 latency** | < 2000 ms | Per-capability `execute()` wall clock |
| **Error rate** | < 1% | Non-timeout failures / total executions |
| **Availability** | > 99.5% | Successful responses / total requests |

## Per-Domain SLO Overrides

Domains that involve external APIs or heavier computation have relaxed targets:

| Domain | p95 Latency | p99 Latency | Error Rate | Notes |
|--------|:-----------:|:-----------:|:----------:|-------|
| `text.*` (baseline) | 100 ms | 500 ms | < 0.5% | Pure Python, deterministic |
| `text.*` (OpenAI) | 2000 ms | 5000 ms | < 2% | Network-bound |
| `data.*` | 100 ms | 500 ms | < 0.5% | Pure Python |
| `code.*` | 200 ms | 1000 ms | < 1% | May involve parsing |
| `model.*` (baseline) | 100 ms | 500 ms | < 0.5% | Local heuristics |
| `model.*` (OpenAI) | 3000 ms | 8000 ms | < 3% | LLM inference |
| `web.*` | 2000 ms | 5000 ms | < 5% | Network-bound, external sites |
| `audio.*` | 5000 ms | 15000 ms | < 5% | Large payloads |
| `agent.*` | 500 ms | 2000 ms | < 2% | May trigger sub-skills |
| `fs.*` | 50 ms | 200 ms | < 0.5% | Local filesystem |
| `email.*` | 2000 ms | 5000 ms | < 3% | SMTP/IMAP latency |

## Configuration

SLO targets can be configured per capability in the binding metadata:

```yaml
# bindings/official/openapi_text_summarize.yaml
metadata:
  slo:
    p95_latency_ms: 2000
    p99_latency_ms: 5000
    error_rate_pct: 2.0
```

The runtime reads these at execution time and records violations as
observability events.

## SLI Collection

SLIs are collected automatically by the runtime:

1. **RuntimeMetrics** (`runtime/metrics.py`) — counters and histograms per capability
2. **OTel spans** (`runtime/otel_integration.py`) — per-step latency with `record_exception`
3. **Audit trail** (`runtime/audit.py`) — hash-chain execution records
4. **Prometheus endpoint** (`GET /v1/metrics`) — exposition format for scraping

### Metrics Available

| Metric | Type | Labels |
|--------|------|--------|
| `capability_execution_duration_ms` | Histogram | `capability_id`, `binding_protocol` |
| `capability_execution_total` | Counter | `capability_id`, `status` |
| `capability_execution_errors_total` | Counter | `capability_id`, `error_code` |
| `step_execution_duration_ms` | Histogram | `skill_id`, `step_id` |

## SLO Violation Alerting

When a capability exceeds its SLO target, the runtime emits:

```python
log_event("slo.violation", {
    "capability_id": "text.content.summarize",
    "sli": "p95_latency_ms",
    "target": 2000,
    "actual": 3500,
    "binding_protocol": "openapi",
})
```

This event is:
- Logged at WARNING level
- Included in the audit trail
- Emitted as an OTel event (when enabled)
- Available via the webhook system (`slo.violation` event type)

## Benchmark Lab Integration

Use `benchmark-lab` to validate SLO compliance:

```bash
# Run 100 iterations and check against SLO targets
agent-skills benchmark-lab text.content.summarize --runs 100

# Compare baseline vs OpenAI binding latency
agent-skills benchmark-lab text.content.summarize --protocols pythoncall,openapi --runs 50
```

## Review Cadence

SLO targets should be reviewed quarterly based on:
- Production metrics (if deployed)
- Benchmark lab results
- New binding additions (new protocols may shift baselines)
- User feedback on acceptable latency

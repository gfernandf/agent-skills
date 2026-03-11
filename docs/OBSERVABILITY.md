# Observability (Step 4)

This project now emits structured JSON logs for runtime orchestration and high-risk baseline services.

## Goals

- Trace each execution with stable event names.
- Measure latency (`duration_ms`) at runtime, capability, and service levels.
- Capture success/failure metadata without changing capability contracts.

## Logger Configuration

- Logger name: `agent_skills`
- Format: single-line JSON per event
- Timestamp field: `ts` (UTC, ISO-like)
- Level env var: `AGENT_SKILLS_LOG_LEVEL` (default: `INFO`)
- Correlation env var support via runtime context: `trace_id` (auto-generated if not provided)
- Max string length in logs: `AGENT_SKILLS_LOG_MAX_STR_LEN` (default: `512`)
- Max collection items in logs: `AGENT_SKILLS_LOG_MAX_ITEMS` (default: `50`)

## Runtime Events

Emitted from the execution pipeline:

- `skill.execute.start`
- `skill.execute.completed`
- `skill.execute.failed`
- `step.execute.start`
- `step.execute.completed`
- `step.execute.failed`
- `capability.execute.start`
- `capability.execute.completed`
- `capability.execute.failed`

Common fields:

- `trace_id`
- `skill_id`
- `step_id`
- `capability_id`
- `binding_id`
- `service_id`
- `duration_ms`
- `error_type`
- `error_message`

## Service Events

Instrumented baseline services:

- `code.execute` via `service.code.execute.start` and `service.code.execute`
- `web.fetch` via `service.web.fetch.start` and `service.web.fetch`
- `pdf.read` via `service.pdf.read.start` and `service.pdf.read`
- `audio.transcribe` via `service.audio.transcribe.start` and `service.audio.transcribe`

Each service event includes status (`completed`, `rejected`, `failed`) and latency.

When service logs are emitted inside runtime execution, `trace_id` is propagated automatically through context.

## Example Log

```json
{"ts":"2026-03-11T10:21:07Z","event":"service.web.fetch","status":"completed","http_status":200,"scheme":"https","host":"www.google.com","duration_ms":595.717}
```

## Notes

- Logging does not alter return payloads for any capability.
- Optional fields are sanitized to JSON-safe values.
- Sensitive fields are redacted based on key names (for example: `token`, `password`, `authorization`, `api_key`, `secret`, `cookie`).
- To reduce verbosity in CI/local runs, set `AGENT_SKILLS_LOG_LEVEL=WARNING`.

## CLI Trace Correlation

You can provide a correlation id from CLI:

- `python cli/main.py run <skill_id> --trace-id my-trace-001`
- `python cli/main.py trace <skill_id> --trace-id my-trace-001`

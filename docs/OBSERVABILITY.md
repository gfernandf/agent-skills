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

### Parallel Step Events

When the DAG scheduler executes steps in parallel (see docs/SCHEDULER.md),
`step.execute.start` / `step.execute.completed` events from concurrent steps
may interleave in the log stream. Correlation is by `step_id` within a given
`trace_id`. The `skill.execute.completed` event is emitted only after all
steps finish.

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

## Skill Execution Audit Records

In addition to runtime logs, skill execution now supports persisted audit records
written as JSONL.

Default path:

- `artifacts/runtime_skill_audit.jsonl`

Override path:

- `AGENT_SKILLS_AUDIT_PATH`

Default mode:

- `AGENT_SKILLS_AUDIT_DEFAULT_MODE` (`standard` by default)

Supported per-execution modes:

- `off`: no persisted audit record for the execution
- `standard`: metadata + hashes only (lightweight)
- `full`: includes redacted payload snapshots per run and per step

Audit records include:

- run metadata (`trace_id`, `skill_id`, status, channel, duration)
- per-step metadata (`step_id`, `uses`, status, duration, binding/service IDs)
- fallback and conformance metadata when available
- hash references for inputs/outputs (`sha256:*`)

Sensitive values are redacted by key-name policy similar to runtime logs.

CLI examples:

- `python cli/main.py run text.simple-summarize --audit-mode standard`
- `python cli/main.py trace text.simple-summarize --audit-mode full`
- `python cli/main.py audit-purge --older-than-days 30`
- `python cli/main.py audit-purge --trace-id <trace-id>`
- `python cli/main.py audit-purge --all`

## End-to-End Validation Checklist

Use this checklist to validate that audit persistence is operational and mode-aware.

1. Reset previous audit records:

```powershell
python cli/main.py audit-purge --all
```

2. Run a multi-step skill in `standard` mode:

```powershell
python cli/main.py trace text.detect-language-and-classify --input-file artifacts/e2e_input_message.json --audit-mode standard
```

Expected:

- Skill completes successfully.
- A new JSONL record is written.
- Record contains `input_hash`/`output_hash` and per-step hashes.
- Record does not include full `inputs`, `outputs`, or per-step payload snapshots.

3. Run the same skill in `full` mode:

```powershell
python cli/main.py run text.detect-language-and-classify --input-file artifacts/e2e_input_message.json --audit-mode full
```

Expected:

- Skill completes successfully.
- A second JSONL record is written.
- Record includes the same hashes plus redacted payload snapshots:
	- top-level `inputs` and `outputs`
	- per-step `resolved_input` and `produced_output`

4. Verify audit file contents:

```powershell
Get-Content artifacts/runtime_skill_audit.jsonl
```

5. Validate user-managed deletion:

```powershell
python cli/main.py audit-purge --trace-id <trace-id>
```

Expected:

- Purge response reports `deleted > 0` for matching records.
- Remaining records are preserved.

## CLI Trace Correlation

You can provide a correlation id from CLI:

- `python cli/main.py run <skill_id> --trace-id my-trace-001`
- `python cli/main.py trace <skill_id> --trace-id my-trace-001`

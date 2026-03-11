# Pre-MCP/OpenAPI Readiness

Date: 2026-03-11

This checklist captures the current system state before integrating MCP/OpenAPI adapters.

## Quality Gates Status

- Functional batch: `33/33`, `0` stubs, `0` errors.
- Contract tests: `33/33` capabilities pass, `99` checks, `0` violations.
- Smoke suite: `8/8` pass.

## Registry Consistency Snapshot

Executed from `agent-skills/tooling`:

- `compute_runtime_coverage.py`
  - total_capabilities: `33`
  - covered_capabilities: `33`
  - uncovered_capabilities: `[]`
  - coverage_ratio: `1.0`
- `compute_runtime_stats.py`
  - capabilities: `33`
  - skills: `31`
  - services: `15`
  - bindings: `33`
  - services_by_kind: `{ "pythoncall": 15 }`
  - bindings_by_source: `{ "official": 33 }`
- `compute_skill_executability.py`
  - total_skills: `31`
  - executable_skills: `31`
  - non_executable_skills: `[]`
  - executability_ratio: `1.0`

## Observability Scope Implemented

- Runtime instrumentation:
  - skill lifecycle
  - step lifecycle
  - capability execution lifecycle
- High-risk service instrumentation:
  - `code.execute`
  - `web.fetch`
  - `pdf.read`
  - `audio.transcribe`
- Trace correlation:
  - end-to-end `trace_id` on skill/step/capability events
  - nested skill execution propagates parent trace id
  - CLI supports `--trace-id` on `run` and `trace`
- Log safety:
  - sensitive key redaction
  - string and collection truncation guards

## CI Consistency Gates

- `smoke.yml` includes a `registry_consistency` job that:
  - validates registry schema and references
  - regenerates catalog and stats
  - fails if regeneration introduces uncommitted diffs (catalog freshness gate)

## Recommended Next Work (Before MCP/OpenAPI)

1. Define and freeze error taxonomy for adapter-facing surfaces (MCP/OpenAPI).
  - Baseline drafted in `docs/OPENAPI_PHASE0_FOUNDATION.md`.
2. Define adapter-level auth and secret handling policy (what can be logged/returned).
  - Baseline drafted in `docs/OPENAPI_PHASE0_FOUNDATION.md`.
3. Add per-capability SLO/SLI targets (latency/error budgets) using current observability fields.

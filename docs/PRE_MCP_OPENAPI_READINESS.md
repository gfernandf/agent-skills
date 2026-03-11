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

## Recommended Next Work (Before MCP/OpenAPI)

1. Add request correlation IDs (`trace_id`) through runtime and service logs.
2. Add structured redaction rules for sensitive fields in input/output logs.
3. Define and freeze error taxonomy for adapter-facing surfaces (MCP/OpenAPI).
4. Add CI check that validates generated registry catalogs are up-to-date.

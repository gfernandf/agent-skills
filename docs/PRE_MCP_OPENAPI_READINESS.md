# Pre-MCP/OpenAPI Readiness

Date: 2026-03-11

This checklist captures the current system state before integrating MCP/OpenAPI adapters.

Historical note: this document captures a pre-integration snapshot.
For the latest baseline numbers, use `docs/PROJECT_STATUS.md`.

## Post-Baseline Update (2026-03-16)

The following gateway-level surfaces are now implemented and validated in
runtime smoke and local product demo flows:

- HTTP gateway routes:
  - `GET /v1/skills/list`
  - `GET /v1/skills/diagnostics`
  - `POST /v1/skills/discover`
  - `POST /v1/skills/{skill_id}/attach`
- MCP tools:
  - `skill.list`, `skill.discover`, `skill.attach`, `skill.diagnostics`, `skill.metrics.reset`
- CLI gateway commands:
  - `list`, `discover`, `attach`, `gateway-diagnostics`, `gateway-reset-metrics`

Validation status additions:

- Gateway parity smoke (`tooling/smoke_gateway_slice3.py`) verifies CLI/HTTP/MCP
  contract alignment, diagnostics, metrics reset, and attach validation behavior.
- Local MCP dual-job orchestration demo (`tooling/demo_mcp_dual_job_trace.py`)
  validates policy-guided decomposition into primary skill execution plus
  sidecar attach workflow.

Notes:

- Discovery ranking remains heuristic and should be combined with product
  selection policy.
- Sidecar execution is skill-category based (`role=sidecar`) and should be
  treated as a generic pattern, not a hard-coded single-skill exception.

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
  - `code.snippet.execute`
  - `web.page.fetch`
  - `pdf.document.read`
  - `audio.speech.transcribe`
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

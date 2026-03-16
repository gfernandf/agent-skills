# Gateway Release Go/No-Go Checklist

Date: 2026-03-16
Scope: Product readiness gates for exposing skills through gateway surfaces.

## Objective

Provide a single release checklist for offering available skills through
CLI/HTTP/MCP with consistent contracts, deterministic behavior, and operable
observability.

## Go/No-Go Gates

All gates below must be `PASS`.

1. Contract parity gate
- CLI, HTTP, and MCP expose the same gateway primitives:
  - list/discover/attach/diagnostics/reset
- Error contract is consistent for invalid requests and missing resources.
- OpenAPI spec matches implemented HTTP routes and request fields.

Verification:
- `python tooling/smoke_gateway_slice3.py --runtime-root . --registry-root ../agent-skill-registry --host-root .`

2. Attach validation gate
- Attach target type is validated against skill classification.
- Target references are validated via attach target index or fallback checks.
- Invalid attaches fail deterministically with clear error payload.

Verification:
- Included in `smoke_gateway_slice3.py`

3. Diagnostics and persistence gate
- `skill.diagnostics` reports process metadata, cache stats, and persistence metadata.
- Metrics reset works and reflects reset counters.
- Diagnostics counters persist across process restarts when persistence is enabled.

Verification:
- Included in `smoke_gateway_slice3.py`

4. Orchestration gate (product-agent pattern)
- Policy-guided decomposition can execute:
  - primary skill execution
  - optional sidecar attach workflow
- Output includes business result and sidecar control/trace result.

Verification:
- `python tooling/demo_mcp_dual_job_trace.py --runtime-root . --registry-root ../agent-skill-registry --host-root artifacts/trace-instance`

5. Security/operability gate
- Auth and rate limits validated for HTTP protected routes.
- Trace IDs and audit behavior are visible and consistent.

Verification:
- `python tooling/verify_customer_http_controls.py`
- `python tooling/verify_customer_facing_neutral.py`

## Policy Notes (Release)

- Discovery ranking is heuristic and must not be interpreted as an absolute
  top-1 mandate.
- Product agents should apply explicit selection policy after `discover`.
- Sidecar behavior should be classification-driven (`role=sidecar`,
  `invocation=attach|both`) and not hard-coded to any single skill id.

## Minimum Release Evidence Bundle

Collect and attach these artifacts to release evidence:

- `artifacts/gateway_slice3.log`
- `artifacts/attach_targets/index.json`
- `artifacts/smoke_report.json` (or equivalent smoke summary)
- Dual-job demo output JSON from `demo_mcp_dual_job_trace.py`

## Go Decision

- `GO`: all gates pass and evidence bundle is complete.
- `NO-GO`: at least one gate fails, or evidence is incomplete.

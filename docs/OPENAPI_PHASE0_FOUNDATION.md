# OpenAPI v1 Phase 0 Foundation

Date: 2026-03-11
Status: Draft baseline for implementation
Scope: Governance and technical foundations for OpenAPI integration without changing capability contracts

## Purpose

This document freezes the technical and governance rules for OpenAPI v1 integration.
It is intentionally focused on adapter design and execution policy, not capability redesign.

## Non-Negotiable Invariants

1. Capabilities are the canonical and stable runtime contract.
2. OpenAPI integration must not require changes to capability definitions.
3. Bindings and services adapt to capabilities, never the reverse.
4. Business logic remains in runtime execution pipeline.
5. Adapter code must only translate transport concerns: HTTP request/response/auth/errors/trace.

## OpenAPI Surfaces

Two independent OpenAPI surfaces are allowed and should not be conflated:

1. Provider-facing OpenAPI
- Used by runtime bindings to call external HTTP APIs.
- Implemented through `service.kind = openapi` and protocol routing.

2. Consumer-facing OpenAPI
- Exposes runtime execution to external users of the skills package.
- Delegates to runtime engine; no duplicated orchestration logic.

## Runtime Reuse Contract

Any OpenAPI work must reuse the existing pipeline:

1. capability and skill resolution
2. binding resolution
3. request mapping
4. protocol routing
5. response mapping
6. output mapping and final validation

No parallel orchestration path should be introduced in the adapter layer.

## Binding Standard for OpenAPI Services (Provider-Facing)

Each OpenAPI binding must define:

1. `id`
2. `capability_id`
3. `service_id`
4. `protocol: openapi`
5. `operation_id` (runtime path selector in current v1 invoker)
6. `request` template using only `input.*` references
7. `response` mapping using only `response.*` references
8. `metadata.method` when method is not POST

Service descriptors for OpenAPI must define at least one of:

1. `base_url`
2. `spec_ref`

## External API Versioning Policy (Consumer-Facing)

1. Public HTTP surface starts at `/v1`.
2. Breaking changes require `/v2`.
3. Capability IDs are stable references, but public endpoint shapes are versioned independently.

## HTTP Error Contract (Frozen for v1)

All adapter errors must use a single envelope:

```json
{
  "error": {
    "code": "string",
    "message": "string",
    "type": "string"
  },
  "trace_id": "string"
}
```

### Deterministic Mapping

1. Invalid request payload or mapping preconditions: `400`
2. Missing skill, capability, binding, or service: `404`
3. Configuration conflicts or invalid runtime topology: `409`
4. Upstream service timeout: `504`
5. Upstream invocation failure (non-timeout): `502`
6. Unhandled internal runtime error: `500`

### Error Safety Rules

1. Do not expose stack traces.
2. Do not expose internal causes in response body.
3. Keep technical detail in logs only, with redaction applied.

## Security and Redaction Policy (Adapter Layer)

1. Authentication is required per endpoint class.
2. Sensitive fields must never be returned in HTTP payloads.
3. Sensitive fields must never be logged in clear text.
4. Existing runtime redaction keys remain authoritative.
5. Adapter must propagate only sanitized error messages.

## Traceability Contract

1. Every request has a `trace_id`.
2. If client provides `trace_id`, preserve it.
3. If absent, generate one and return it.
4. Include `trace_id` in:
- HTTP response body or headers
- runtime lifecycle logs
- service invocation logs

## Phase 0 Exit Criteria

Phase 0 is considered complete when:

1. This foundation is approved by maintainers.
2. Smoke capability subset for OpenAPI Phase 1 is selected (5 to 8 capabilities).
3. HTTP error mapping table is approved and referenced by adapter implementation.
4. Security and redaction policy is approved for adapter responses and logs.
5. CI plan for OpenAPI contract tests is defined (implementation can happen in later phase).

## Out of Scope for Phase 0

1. Migrating all capabilities to OpenAPI bindings.
2. Implementing full consumer-facing OpenAPI server.
3. Capability schema redesign.
4. Performance tuning beyond baseline timeout and limits.

## Next Step

Use this document as the gate for Phase 1 implementation on smoke capabilities.
Execution planning for that subset is documented in `docs/OPENAPI_PHASE1_SMOKE_PLAN.md`.
Construction sequencing by scope and commit boundaries is documented in `docs/OPENAPI_CONSTRUCTION_PACKAGES.md`.

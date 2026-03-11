# OpenAPI Error and Security Baseline

Date: 2026-03-11
Status: Construction package 3 baseline
Scope: Adapter-facing HTTP error contract and minimum security rules

## Purpose

Freeze a deterministic error contract and baseline safety rules before expanding OpenAPI capability population.

## Error Contract

The adapter-facing payload uses a single envelope:

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

## Deterministic Mapping

Current mapper implementation: `runtime/openapi_error_contract.py`

1. `SkillNotFoundError`, `CapabilityNotFoundError` -> `404 not_found`
2. `InputMappingError`, `ReferenceResolutionError`, `OutputMappingError` -> `400 invalid_request`
3. `FinalOutputValidationError`, `InvalidSkillSpecError`, `InvalidCapabilitySpecError` -> `409 invalid_configuration`
4. `CapabilityExecutionError` / `StepExecutionError` with timeout root cause -> `504 upstream_timeout`
5. `CapabilityExecutionError` / `StepExecutionError` non-timeout upstream failures -> `502 upstream_failure`
6. other `RuntimeErrorBase` -> `500 runtime_error`
7. unknown exceptions -> `500 internal_error`

## Safety Rules

1. Never expose stack traces in HTTP responses.
2. Never expose nested causes or sensitive internals in HTTP payloads.
3. Error messages are sanitized and length-limited before returning.
4. Detailed diagnostics remain in structured logs, with existing redaction controls.

## Verification

Run:

- `python tooling/verify_openapi_error_contract.py`

This script verifies deterministic mapping and fallback behavior.

## Next Package Dependencies

Package 4 (CI OpenAPI gate) should include this verification script in its job matrix.

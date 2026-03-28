# Error Taxonomy

> Frozen error codes for all adapter-facing surfaces (HTTP, MCP, LLM adapters).

## Design Principles

1. **Stable codes** — error codes are part of the public contract; changes require a deprecation cycle.
2. **No stack traces** — adapter responses never leak implementation details.
3. **Machine-readable** — every error includes `code`, `type`, `message`, and optional `hint`.
4. **Remediation-first** — hints tell the caller how to fix the problem, not just what broke.

## Error Code Reference

### Client Errors (4xx)

| Code | HTTP | MCP | Description |
|------|------|-----|-------------|
| `not_found` | 404 | `MethodNotFound` | Skill or capability not found |
| `invalid_request` | 400 | `InvalidParams` | Bad input mapping, reference, or options |
| `max_depth_exceeded` | 400 | `InvalidParams` | Nested skill depth limit reached |
| `safety_denied` | 403 | `InvalidRequest` | Safety gate or trust level blocked execution |
| `confirmation_required` | 428 | `InvalidRequest` | Human confirmation needed before execution |
| `invalid_configuration` | 409 | `InternalError` | Skill/capability YAML is malformed |
| `conformance_unmet` | 412 | `InvalidParams` | No binding meets the conformance profile |
| `unauthorized` | 401 | — | Missing or invalid credentials |
| `forbidden` | 403 | — | Insufficient role for the requested operation |
| `rate_limited` | 429 | — | Rate limit exceeded |

### Server Errors (5xx)

| Code | HTTP | MCP | Description |
|------|------|-----|-------------|
| `gate_execution_failure` | 503 | `InternalError` | Safety gate infra failure (not a deny) |
| `step_timeout` | 504 | `InternalError` | Step exceeded `timeout_seconds` |
| `upstream_timeout` | 504 | `InternalError` | External service did not respond in time |
| `upstream_failure` | 502 | `InternalError` | External service returned an error |
| `runtime_error` | 500 | `InternalError` | Unexpected runtime failure |
| `internal_error` | 500 | `InternalError` | Unclassified server error |

## HTTP Error Payload

```json
{
  "error": {
    "code": "not_found",
    "type": "SkillNotFoundError",
    "message": "Skill 'text.nonexistent' not found.",
    "hint": "Verify the skill ID with 'agent-skills list'."
  },
  "trace_id": "abc-123"
}
```

## MCP Error Payload

MCP errors use JSON-RPC 2.0 error codes. The `data` field contains the
agent-skills error detail:

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "error": {
    "code": -32602,
    "message": "Capability 'text.nonexistent' not found.",
    "data": {
      "agent_skills_code": "not_found",
      "type": "CapabilityNotFoundError",
      "hint": "Verify the capability ID with 'agent-skills explain-capability <id>'."
    }
  }
}
```

## LLM Adapter Error Payload

All `execute_*_tool_call()` functions return errors as JSON strings:

```json
{
  "error": "CapabilityNotFoundError: Capability 'text.nonexistent' not found.",
  "code": "not_found"
}
```

## Error → Code Mapping (Implementation)

The canonical mapping lives in `runtime/openapi_error_contract.py`:

| Exception Class | → Code |
|----------------|--------|
| `SkillNotFoundError` | `not_found` |
| `CapabilityNotFoundError` | `not_found` |
| `InputMappingError` | `invalid_request` |
| `ReferenceResolutionError` | `invalid_request` |
| `OutputMappingError` | `invalid_request` |
| `AttachValidationError` | `invalid_request` |
| `InvalidExecutionOptionsError` | `invalid_request` |
| `MaxSkillDepthExceededError` | `max_depth_exceeded` |
| `SafetyTrustLevelError` | `safety_denied` |
| `SafetyGateFailedError` | `safety_denied` |
| `GateDeniedError` | `safety_denied` |
| `SafetyConfirmationRequiredError` | `confirmation_required` |
| `GateExecutionError` | `gate_execution_failure` |
| `StepTimeoutError` | `step_timeout` |
| `FinalOutputValidationError` | `invalid_configuration` |
| `InvalidSkillSpecError` | `invalid_configuration` |
| `InvalidCapabilitySpecError` | `invalid_configuration` |
| `BindingExecutionError` (conformance) | `conformance_unmet` |
| `CapabilityExecutionError` | `upstream_failure` |
| `StepExecutionError` | `upstream_failure` |
| `NestedSkillExecutionError` | `upstream_failure` |
| `RuntimeErrorBase` (other) | `runtime_error` |
| Any other `Exception` | `internal_error` |

## Extending the Taxonomy

To add a new error code:

1. Add the exception class in `runtime/errors.py`
2. Add the mapping in `runtime/openapi_error_contract.py`
3. Add a remediation hint in `_REMEDIATION_HINTS`
4. Update this document
5. Bump the changelog

Error codes, once published, must not change meaning or be removed without a deprecation notice.

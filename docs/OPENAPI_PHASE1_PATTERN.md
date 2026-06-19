# OpenAPI Phase 1 Population - Implementation Pattern

## Overview

This document describes the pattern used to add Phase 1 real service implementations for each capability in the smoke test suite.

## Pattern Template

For each capability, you need to create 3 files:

### 1. Service Configuration YAML
**Location**: `services/official/{capability}_openapi_local.yaml`

```yaml
id: {capability}_openapi_local
kind: openapi
base_url: http://127.0.0.1:{PORT}
spec_ref: services/official/specs/{capability}_openapi_local.yaml

metadata:
  description: "Local real OpenAPI provider for {capability} pilot integration."
  maintained_by: "agent-skills"
  status: pilot
  purpose: phase1-real-local
  timeout_seconds: {TIMEOUT}
```

**Rules**:
- Use unique ports: 8780 (data.schema.validate), 8781 (text.summarize), 8782 (code.execute), etc.
- status: pilot (not experimental)
- purpose: phase1-real-local (consistent tag)

### 2. OpenAPI Spec YAML
**Location**: `services/official/specs/{capability}_openapi_local.yaml`

```yaml
openapi: 3.0.3
info:
  title: {Capability Title} Local API
  version: 1.0.0
  description: Local provider for pilot real-service integration of {capability}.
servers:
  - url: http://127.0.0.1:{PORT}
paths:
  /health:
    get:
      operationId: health
      summary: Health probe endpoint.
      responses:
        '200':
          description: Service health.
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
                    enum: [ok, degraded, error]
  /{operation}:
    post:
      operationId: {operation}
      summary: {Summary description}
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [{REQUIRED_FIELDS}]
              properties:
                {FIELDS}
      responses:
        '200':
          description: Success response.
          content:
            application/json:
              schema:
                type: object
                required: [result, status]
                properties:
                  result:
                    type: object
                    description: Operation result (shape varies by capability)
                  status:
                    type: string
                    enum: [ok, partial, error]
                  trace_ref:
                    type: string
```

**Rules**:
- Include `/health` endpoint for liveness checks
- Main operation endpoint at `/{operation}` (matching binding operationId)
- Standard response structure: `result` + `status` + optional `trace_ref`
- status enum: ok | partial | error

### 3. Binding Configuration YAML
**Location**: `bindings/official/{capability}/openapi_{capability_underscores}_local.yaml`

```yaml
id: openapi_{capability_underscores}_local

capability: {capability}
service: {capability}_openapi_local
protocol: openapi
operation: {operation}

request:
  {field1}: input.{field1}
  {field2}: input.{field2}

response:
  result: response.result
  status: response.status
  trace_ref: response.trace_ref

metadata:
  method: POST
  description: "Local OpenAPI pilot binding for {capability}."
  status: pilot
  timeout_seconds: {TIMEOUT}
```

**Rules**:
- Match service ID from service YAML
- operation must match OpenAPI operationId
- Request mapping: input field to request body field
- Response mapping: response field to output field
- Use standard status field for health

### 4. Provider Implementation (Optional)
**Location**: `providers/{capability}_openapi_local.py`

Pattern:
- FastAPI server on specified port
- /health endpoint returning `{status: ok}`
- Main operation endpoint implementing basic logic
- Can be stub (mock responses) or real implementation
- Support graceful startup/shutdown for CI integration

## Capabilities to Implement (Phase 1)

Sequence and ports:

1. text.content.summarize - 8781 ✅ DONE (commit ddcd383)
2. code.snippet.execute - 8782
3. web.page.fetch - 8783
4. pdf.document.read - 8784
5. audio.speech.transcribe - 8785
6. fs.file.read - 8786
7. agent.input.route - 8787

---

## Mapping Table

| Capability | YAML ID | Port | Operation | Status |
|---|---|---|---|---|
| data.schema.validate | data_schema_validate | 8780 | validate | ✅ DONE |
| text.content.summarize | text_summarize | 8781 | summarize | ✅ DONE |
| code.snippet.execute | code_execute | 8782 | execute | ✅ DONE |
| web.page.fetch | web_fetch | 8783 | fetch | ✅ DONE |
| pdf.document.read | pdf_read | 8784 | read | ✅ DONE |
| audio.speech.transcribe | audio_transcribe | 8785 | transcribe | ✅ DONE |
| fs.file.read | fs_read | 8786 | read | ✅ DONE |
| agent.input.route | agent_route | 8787 | route | ✅ DONE |

---

## Implementation Checklist (per capability)

- [ ] Create `services/official/{capability}_openapi_local.yaml`
- [ ] Create `services/official/specs/{capability}_openapi_local.yaml`
- [ ] Create `bindings/official/{capability}/openapi_{capability_underscores}_local.yaml`
- [ ] Create `providers/{capability}_openapi_local.py` (optional stub)
- [ ] Test locally: `python providers/{capability}_openapi_local.py --port {PORT}`
- [ ] Verify endpoint health: `curl http://127.0.0.1:{PORT}/health`
- [ ] Commit: `git add` files + `git commit -m "feat: OpenAPI Phase 1 - {capability} real service"`
- [ ] Update OPENAPI_POPULATION_CHECKLIST.md status

---

## Template Replication Script

To batch-create remaining 6 capabilities, follow the pattern template above and:

1. Copy text.summarize files as template
2. Replace capability name, port, operation name
3. Adapt request/response schemas based on capability contract
4. Commit per capability or in batch

---

## Testing Integration

In smoke test CI:
1. Start provider on allocated port (or use mock if provider unavailable)
2. Test binding resolution:
   ```bash
   python tooling/verify_smoke_capabilities.py --capability {capability}
   ```
3. Verify binding can execute:
   ```bash
   python tooling/verify_openapi_{capability}.py --binding openapi_{capability_underscores}_local
   ```

---

## Reference Implementation

See commit ddcd383 for text.summarize as the reference for:
- Service config structure
- Full OpenAPI spec with /health + operation endpoint
- Binding config mapping
- Python provider with FastAPI pattern

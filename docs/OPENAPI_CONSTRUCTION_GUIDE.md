# OpenAPI Construction Guide

Date: 2026-03-11  
Status: Operational runbook for Package 6 + population phase  
Scope: Copy-paste templates and validation steps for adding new OpenAPI bindings and services

## Overview

This guide enables any team member to safely add a new OpenAPI binding to an existing capability without asking questions.

The construction phase established three parallel paths for the `data.schema.validate` capability:
1. **Official (Python-based)**: Default, always available, kernel-integrated
2. **Mock (HTTP-based)**: CI-safe, no external dependency, for testing harness
3. **Real Pilot (HTTP-based)**: Local service, manual validation, for operational pilots

This guide shows how to add paths 2 and 3 to any other capability.

---

## Part 1: Add Mock OpenAPI Binding (CI-Safe)

Use this when you want to test a capability via HTTP without external service dependency.

### Step 1: Create Mock Scenario JSON

**File**: `tooling/openapi_scenarios/{capability_id}.openapi.mock.json`

**Template**:
```json
{
  "capability_id": "data.schema.validate",
  "binding_id": "openapi_data_schema_validate_mock",
  "id": "data.schema.validate.openapi.mock",
  "input": {
    "data": { "name": "Alice", "age": 30 },
    "schema": { "type": "object", "required": ["name"] }
  },
  "expected_output": {
    "valid": true,
    "errors": []
  },
  "mock_server": {
    "type": "data_schema_validate",
    "host": "127.0.0.1",
    "port": 8765
  },
  "timeout_seconds": 5,
  "notes": "Mock server validates JSON schema; use same test cases as pythoncall binding"
}
```

**Instructions**:
- Replace `capability_id` with target capability name
- Replace `binding_id` with `openapi_{capability_id_underscored}_mock`
- Replace `id` with `{capability_id}.openapi.mock`
- Set `input` to match the capability's request schema (inspect capability descriptor in registry)
- Set `expected_output` to match the capability's response schema
- Set `mock_server.type` to match handler class name in [tooling/openapi_harness/mocks.py](tooling/openapi_harness/mocks.py)
- If new handler type needed, see **Part 3** below

### Step 2: Create Mock Service Descriptor

**File**: `services/official/{capability_id}_openapi_mock.yaml`

**Template**:
```yaml
# Mock HTTP service for {capability_id} capability
# Status: experimental (mock only, CI-safe, no external dependency)
id: data_schema_validate_openapi_mock
name: "Data Schema Validate (OpenAPI Mock)"
kind: openapi
protocol: openapi
baseUrl: http://127.0.0.1:8765
spec:
  path: specs/data_schema_validate_openapi_mock.yaml
timeout_seconds: 5
metadata:
  kind: mock
  provider_type: local_http
  managed_by: agent-skills
  notes: "Reusable mock server; add handler in openapi_harness/mocks.py"
```

**Instructions**:
- Replace `id` and `name` with capability name
- Keep `baseUrl: http://127.0.0.1:{port}` (port matches mock_server.port in scenario)
- Point `spec.path` to OpenAPI spec file (see Step 3)
- `timeout_seconds` should match scenario timeout

### Step 3: Create OpenAPI Spec (Mock)

**File**: `services/official/specs/{capability_id}_openapi_mock.yaml`

**Template**:
```yaml
openapi: 3.0.3
info:
  title: Data Schema Validate (Mock)
  version: 1.0.0
  description: Mock HTTP service for schema validation
servers:
  - url: http://127.0.0.1:8765

paths:
  /validate:
    post:
      operationId: validate
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required:
                - data
                - schema
              properties:
                data:
                  type: object
                  description: Data to validate
                schema:
                  type: object
                  description: JSON Schema to validate against
      responses:
        "200":
          description: Validation result
          content:
            application/json:
              schema:
                type: object
                required:
                  - valid
                  - errors
                properties:
                  valid:
                    type: boolean
                  errors:
                    type: array
                    items:
                      type: string
        "400":
          description: Bad request
        "504":
          description: Timeout or execution error
```

**Instructions**:
- Replace title and operation name with capability name
- Define POST path matching handler in mocks.py
- Define requestBody matching capability input schema
- Define 200 response matching capability output schema
- Keep error responses as shown (400, 504)

### Step 4: Create Mock Binding

**File**: `bindings/official/{capability_id}/openapi_{capability_id_underscored}_mock.yaml`

**Template**:
```yaml
id: openapi_data_schema_validate_mock
capability_id: data.schema.validate
protocol: openapi
service:
  id: data_schema_validate_openapi_mock
  kind: openapi
status: experimental
metadata:
  kind: mock
  managed_by: agent-skills
  notes: |
    CI-safe mock binding. Runs local mock HTTP server.
    Use for: testing harness, CI verification, no external dependency
    Do NOT use in production without real service backing.
```

**Instructions**:
- `id` must match `binding_id` in scenario
- `capability_id` must match target capability
- `service.id` must match service descriptor id from Step 2
- `status: experimental` (required for mocks)

### Step 5: Register Mock Handler

**File**: `tooling/openapi_harness/mocks.py`

**Template** (add to file):
```python
class NewCapabilityHandler(BaseHTTPRequestHandler):
    """Mock handler for {capability_id} capability"""
    
    def do_POST(self):
        if self.path == "/validate":
            try:
                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length)
                request = json.loads(body)
                
                # Your validation logic here
                result = {
                    "valid": True,
                    "errors": []
                }
                
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(result).encode())
            except Exception as e:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode())
        else:
            self.send_response(404)
            self.end_headers()
```

Then register in HANDLER_BY_TYPE:
```python
HANDLER_BY_TYPE = {
    "data_schema_validate": DataSchemaValidateHandler,
    "new_capability": NewCapabilityHandler,  # ADD THIS LINE
}
```

**Instructions**:
- Class name must match `type` in scenario mock_server config
- Implement POST handler for capability endpoint
- Return response matching OpenAPI spec response schema
- Register in HANDLER_BY_TYPE dict at end of mocks.py

### Step 6: Verify Mock Binding

**Command**:
```bash
python cli/main.py openapi verify-bindings \
  --scenarios-dir tooling/openapi_scenarios \
  --report-file artifacts/mock-{capability_id}-report.json
```

**Expected Output**:
```
{
  "total": 1,
  "passed": 1,
  "failed": 0,
  "results": [{
    "id": "{capability_id}.openapi.mock",
    "passed": true,
    "outputs": { "valid": true, "errors": [] }
  }]
}
```

**Troubleshooting**:
- If mock server fails to start: Check port 8765 is not in use
- If scenario fails: Inspect mock handler logic in mocks.py
- If binding not found: Verify binding id matches scenario binding_id

---

## Part 2: Add Real OpenAPI Binding (Local Service)

Use this when you have a real HTTP service running locally for operational validation.

### Step 1: Create Real Service Provider (Python)

**File**: `tooling/openapi_providers/{capability_id}_service.py`

**Template**:
```python
#!/usr/bin/env python3
"""Local HTTP provider for {capability_id} capability"""

import json
import argparse
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading
import time

class ServiceHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok"}).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == "/validate":
            try:
                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length)
                request = json.loads(body)
                
                # Your business logic here
                result = {"valid": True, "errors": []}
                
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(result).encode())
            except Exception as e:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # Suppress default logging


def run_server(host, port):
    server = HTTPServer((host, port), ServiceHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(f"{port} service listening on http://{host}:{port}")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print(f"\nShutting down {port} service")
        server.shutdown()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8780)
    args = parser.parse_args()
    run_server(args.host, args.port)
```

**Instructions**:
- Replace `{capability_id}` with target capability
- Implement POST handler with actual business logic
- Implement GET /health for health checks
- Test locally with `python tooling/openapi_providers/{capability_id}_service.py`

### Step 2: Create Real Service Descriptor

**File**: `services/official/{capability_id}_openapi_local.yaml`

**Template**:
```yaml
id: data_schema_validate_openapi_local
name: "Data Schema Validate (OpenAPI Local)"
kind: openapi
protocol: openapi
baseUrl: http://127.0.0.1:8780
spec:
  path: specs/data_schema_validate_openapi_local.yaml
timeout_seconds: 10
status: pilot
metadata:
  kind: real_local
  provider_type: local_http_service
  managed_by: agent-skills
  notes: "Requires local service running on port 8780. For operational pilots only."
```

**Instructions**:
- `id` and `name` with capability name
- `baseUrl` with service port (8780 for first real service, increment for others: 8781, 8782, etc.)
- `status: pilot` (marks as pilot until ready for stable)

### Step 3: Create OpenAPI Spec (Real)

**File**: `services/official/specs/{capability_id}_openapi_local.yaml`

Same structure as mock spec (Part 1, Step 3) but with real endpoint paths.

### Step 4: Create Real Binding

**File**: `bindings/official/{capability_id}/openapi_{capability_id_underscored}_local.yaml`

**Template**:
```yaml
id: openapi_data_schema_validate_local
capability_id: data.schema.validate
protocol: openapi
service:
  id: data_schema_validate_openapi_local
  kind: openapi
status: pilot
metadata:
  kind: real_local
  managed_by: agent-skills
  notes: |
    Real service binding for operational pilot.
    Requires: python tooling/openapi_providers/{capability_id}_service.py
    Use for: end-to-end validation, operational testing
```

**Instructions**:
- `id` must uniquely identify real binding
- `status: pilot` until verified for stable use

### Step 5: Create Real Service Scenario

**File**: `tooling/openapi_scenarios_real/{capability_id}.openapi.local.json`

**Template**:
```json
{
  "capability_id": "data.schema.validate",
  "binding_id": "openapi_data_schema_validate_local",
  "id": "data.schema.validate.openapi.local",
  "input": {
    "data": { "name": "Alice", "age": 30 },
    "schema": { "type": "object", "required": ["name"] }
  },
  "expected_output": {
    "valid": true,
    "errors": []
  },
  "timeout_seconds": 10,
  "notes": "Real service scenario; requires local provider running on port {port}"
}
```

### Step 6: Create E2E Verification Script

**File**: `tooling/verify_openapi_{capability_id}_local_real.py`

**Template**:
```python
#!/usr/bin/env python3
"""E2E verification for {capability_id} real service pilot"""

import json
import subprocess
import time
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent

def main():
    # Start provider
    provider_script = PROJECT_ROOT / "tooling" / "openapi_providers" / "{capability_id}_service.py"
    provider_proc = subprocess.Popen(
        ["python", str(provider_script), "--host", "127.0.0.1", "--port", "8780"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    # Wait for health
    time.sleep(0.5)
    
    try:
        # Run scenario
        scenario_file = PROJECT_ROOT / "tooling" / "openapi_scenarios_real" / "{capability_id}.openapi.local.json"
        result = subprocess.run(
            [
                "python", str(PROJECT_ROOT / "tooling" / "verify_openapi_bindings.py"),
                str(scenario_file)
            ],
            capture_output=True,
            text=True
        )
        
        print(result.stdout)
        exit(result.returncode)
    finally:
        provider_proc.terminate()
        provider_proc.wait(timeout=5)


if __name__ == "__main__":
    main()
```

**Instructions**:
- Replace `{capability_id}` with target capability
- Port should be incremented per service (8780, 8781, 8782, etc.)
- Test with: `python tooling/verify_openapi_{capability_id}_local_real.py`

### Step 7: Verify Real Binding

**Manual Test**:
```bash
# Terminal 1: Start provider
python tooling/openapi_providers/{capability_id}_service.py

# Terminal 2: Run E2E verification
python tooling/verify_openapi_{capability_id}_local_real.py
```

**Expected Output**:
- Provider reports listening on `http://127.0.0.1:8780`
- Verification reports `{capability_id}.openapi.local: PASS`

---

## Part 3: Adding New Mock Handler Type

When a capability requires unique mock logic not covered by existing handlers:

### Pattern: Implement Handler Class

**Location**: `tooling/openapi_harness/mocks.py`

**Step 1**: Add handler class
```python
class YourCapabilityHandler(BaseHTTPRequestHandler):
    """Mock handler for your capability"""
    
    def do_POST(self):
        if self.path == "/endpoint":
            # Implement handler
            pass
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        pass  # Suppress logging
```

**Step 2**: Register in HANDLER_BY_TYPE
```python
HANDLER_BY_TYPE = {
    "data_schema_validate": DataSchemaValidateHandler,
    "your_capability": YourCapabilityHandler,  # ADD HERE
}
```

**Step 3**: Use in scenario
```json
{
  "mock_server": {
    "type": "your_capability",
    "host": "127.0.0.1",
    "port": 8765
  }
}
```

---

## Part 4: Validation Checklist

After adding mock or real binding:

- [ ] Scenario JSON created with valid input/output
- [ ] Service descriptor created with baseUrl and spec path
- [ ] OpenAPI spec created with correct paths and schemas
- [ ] Binding created with correct capability_id and service.id
- [ ] Mock handler (if mock): registered in HANDLER_BY_TYPE
- [ ] Provider script (if real): accepts --host --port arguments
- [ ] Scenario runs without errors: `python cli/main.py openapi verify-bindings {scenario_path}`
- [ ] Response matches expected_output exactly
- [ ] Binding status matches intent: `experimental` for mock, `pilot` for real
- [ ] Timeout and port defaults documented in metadata.notes

---

## Part 5: Integration with Smoke & Contract Tests

Once binding verified:

### Update Smoke Test
- No action required; smoke test automatically uses default binding (pythoncall)
- OpenAPI bindings are alternatives, not defaults

### Update Contract Tests
- No action required; contracts already pass with pythoncall binding
- OpenAPI bindings run in parallel verification suite, not contract suite

### Adding to CI Verification
- Mock scenarios: automatically included in `python cli/main.py openapi verify-bindings --all`
- Real scenarios: manual testing only, not in CI (requires running service)

---

## Part 6: Common Patterns

### Pattern: Optional Request Fields
```json
{
  "input": {
    "required_field": "value",
    "optional_field": null
  }
}
```

Handler should treat null as field not provided.

### Pattern: Paginated Responses
```json
{
  "expected_output": {
    "items": [],
    "page": 1,
    "total": 0
  }
}
```

### Pattern: Error Cases
Use multiple scenarios per capability:
- `{capability}.openapi.mock.success.json` - happy path
- `{capability}.openapi.mock.invalid_input.json` - error case
- etc.

---

## Summary

To add a new OpenAPI binding in ~15 minutes:

1. Copy scenario template → `tooling/openapi_scenarios/{id}.openapi.mock.json`
2. Copy service template → `services/official/{id}_openapi_mock.yaml`
3. Copy spec template → `services/official/specs/{id}_openapi_mock.yaml`
4. Copy binding template → `bindings/official/{id}/openapi_{id}_mock.yaml`
5. Add mock handler to `tooling/openapi_harness/mocks.py` (if new type)
6. Verify: `python cli/main.py openapi verify-bindings {scenario_path}`
7. Repeat Part 2 for real service (optional, for pilots)

All paths follow consistent naming convention and can be templated for new capabilities.

# OpenAPI Population Checklist

Date: 2026-03-11  
Status: Operational gates for capability population phase  
Scope: Gate criteria, verification steps, and transition rules for each smoke capability

## Overview

This checklist guides the population phase: systematically adding OpenAPI bindings to each smoke capability until all have mock + real service paths.

**Starting Point**: Construction phase complete
- ✅ OpenAPI runtime hardened (invoker, error contract)
- ✅ Verification infrastructure deployed (harness, mocks, CI)
- ✅ First real service pilot complete (data.schema.validate)
- ✅ Documentation created (construction guide, this checklist)

**Target State**: Each capability has three parallel binding paths:
1. **Official (Python-based)**: Default, always active, kernel-integrated
2. **Mock (HTTP-based)**: CI-safe, alternative, tested in harness
3. **Real Service (HTTP-based)**: Operational pilot, local deployment

**Constraints**:
- No capability contract changes allowed
- Official (pythoncall) remains default until explicitly changed
- Each binding must pass verification before marking complete
- Real service pilots require local provider executable
- All changes committed and CI green before moving to next capability

---

## Capabilities Queue (Smoke Test Order)

Based on [tooling/verify_smoke_capabilities.py](tooling/verify_smoke_capabilities.py):

### 1. text.summarize
- **Status**: 🟡 Mock Complete
- **Smoke Status**: ✅ PASS (official/pythoncall)
- **Mock Binding**: ✅ PASS (openapi_text_summarize_mock)
- **Real Service**: ⚪ TODO
- **Notes**: Core text capability; consider mock first, then simple text provider

### 2. code.execute
- **Status**: 🟡 Mock Complete
- **Smoke Status**: ✅ PASS (official/pythoncall)
- **Mock Binding**: ✅ PASS (openapi_code_execute_mock)
- **Real Service**: ⚪ TODO
- **Notes**: Execution capability; mock can return static code output

### 3. web.fetch
- **Status**: 🟡 Mock Complete
- **Smoke Status**: ✅ PASS (official/pythoncall)
- **Mock Binding**: ✅ PASS (openapi_web_fetch_mock)
- **Real Service**: ⚪ TODO
- **Notes**: Fetches external URLs; mock can return hardcoded HTML

### 4. pdf.read
- **Status**: 🟡 Mock Complete
- **Smoke Status**: ✅ PASS (official/pythoncall)
- **Mock Binding**: ✅ PASS (openapi_pdf_read_mock)
- **Real Service**: ⚪ TODO
- **Notes**: PDF extraction; mock returns mock text content

### 5. audio.transcribe
- **Status**: 🟡 Mock Complete
- **Smoke Status**: ✅ PASS (official/pythoncall)
- **Mock Binding**: ✅ PASS (openapi_audio_transcribe_mock)
- **Real Service**: ⚪ TODO
- **Notes**: Audio to text; mock returns static transcription

### 6. fs.read
- **Status**: 🟡 Mock Complete
- **Smoke Status**: ✅ PASS (official/pythoncall)
- **Mock Binding**: ✅ PASS (openapi_fs_read_mock)
- **Real Service**: ⚪ TODO
- **Notes**: File system read; mock returns test file contents

### 7. data.schema.validate
- **Status**: ✅ COMPLETE
- **Smoke Status**: ✅ PASS (official/pythoncall)
- **Mock Binding**: ✅ PASS (openapi_data_schema_validate_mock)
- **Real Service**: ✅ PASS (openapi_data_schema_validate_local)
- **Commits**: 79a3429, 3eeea9b, 72b52c7, b07ba84, 49665f3
- **Notes**: Reference implementation; copy pattern for remaining capabilities

### 8. agent.route
- **Status**: 🟡 Mock Complete
- **Smoke Status**: ✅ PASS (official/pythoncall)
- **Mock Binding**: ✅ PASS (openapi_agent_route_mock)
- **Real Service**: ⚪ TODO
- **Notes**: Agent routing; mock can return static routing decision

---

## Population Workflow

### Pre-Population Gate ✅

Verify these conditions before starting:

```bash
# Verify working tree clean
git status --short  # Should be empty

# Verify smoke tests still pass
python tooling/verify_smoke_capabilities.py --report-file /tmp/smoke.json

# Verify contract tests still pass
python tooling/test_capability_contracts.py

# Verify OpenAPI infrastructure passing
python cli/main.py openapi verify-bindings --all
python cli/main.py openapi verify-invoker
python cli/main.py openapi verify-errors

# Verify real pilot passes
python tooling/verify_openapi_data_schema_validate_local_real.py
```

Expected output: All tests green ✅

### Per-Capability Gate ✅

For each capability in queue (text.summarize → agent.route):

#### Phase 1: Mock Binding & Scenario (20 min)

```bash
# 1) Copy construction guide templates to new files
cp docs/OPENAPI_CONSTRUCTION_GUIDE.md /tmp/ref.md

# 2) Create scenario
cat > tooling/openapi_scenarios/{capability_id}.openapi.mock.json << 'EOF'
{
  "capability_id": "{capability_id}",
  "binding_id": "openapi_{capability_id_underscored}_mock",
  ...
}
EOF

# 3) Create service descriptor
cat > services/official/{capability_id}_openapi_mock.yaml << 'EOF'
id: {capability_id}_openapi_mock
...
EOF

# 4) Create OpenAPI spec
cat > services/official/specs/{capability_id}_openapi_mock.yaml << 'EOF'
openapi: 3.0.3
...
EOF

# 5) Create binding
cat > bindings/official/{capability_id}/openapi_{capability_id_underscored}_mock.yaml << 'EOF'
id: openapi_{capability_id_underscored}_mock
...
EOF

# 6) Add mock handler to mocks.py
# Edit tooling/openapi_harness/mocks.py: add handler class + register in HANDLER_BY_TYPE

# 7) Verify mock binding
python cli/main.py openapi verify-bindings tooling/openapi_scenarios/{capability_id}.openapi.mock.json

# Expected output: PASS
```

#### Phase 1 Completion Gate 🚪

Before committing Phase 1:

```bash
# A) Verify new binding passes in isolation
python cli/main.py openapi verify-bindings tooling/openapi_scenarios/{capability_id}.openapi.mock.json

# B) Verify no regression in smoke tests
python tooling/verify_smoke_capabilities.py

# C) Verify no regression in contract tests
python tooling/test_capability_contracts.py

# D) Verify no regression in other OpenAPI scenarios
python cli/main.py openapi verify-bindings --all

# E) Verify all CLI commands still pass
python cli/main.py openapi verify-invoker
python cli/main.py openapi verify-errors
```

Expected output: All tests green ✅

#### Phase 1 Commit

```bash
git add \
  tooling/openapi_scenarios/{capability_id}.openapi.mock.json \
  services/official/{capability_id}_openapi_mock.yaml \
  services/official/specs/{capability_id}_openapi_mock.yaml \
  bindings/official/{capability_id}/openapi_{capability_id_underscored}_mock.yaml \
  tooling/openapi_harness/mocks.py

git commit -m "openapi: add mock binding for {capability_id}"
```

---

#### Phase 2: Real Service Provider & E2E (30 min)

```bash
# 1) Create provider executable
cat > tooling/openapi_providers/{capability_id}_service.py << 'EOF'
#!/usr/bin/env python3
...
EOF

# 2) Test provider locally (Terminal 1)
python tooling/openapi_providers/{capability_id}_service.py --host 127.0.0.1 --port 8{781+N}

# Verify output: "service listening on http://127.0.0.1:8{port}"

# 3) Create service descriptor for real
cat > services/official/{capability_id}_openapi_local.yaml << 'EOF'
id: {capability_id}_openapi_local
...
status: pilot
EOF

# 4) Create OpenAPI spec for real
cat > services/official/specs/{capability_id}_openapi_local.yaml << 'EOF'
openapi: 3.0.3
...
EOF

# 5) Create binding for real
cat > bindings/official/{capability_id}/openapi_{capability_id_underscored}_local.yaml << 'EOF'
id: openapi_{capability_id_underscored}_local
...
status: pilot
EOF

# 6) Create real service scenario
cat > tooling/openapi_scenarios_real/{capability_id}.openapi.local.json << 'EOF'
{
  "capability_id": "{capability_id}",
  "binding_id": "openapi_{capability_id_underscored}_local",
  ...
  "timeout_seconds": 10
}
EOF

# 7) Create E2E verification script
cat > tooling/verify_openapi_{capability_id}_local_real.py << 'EOF'
#!/usr/bin/env python3
...
EOF

# 8) Test E2E verification (Terminal 2, while provider running in Terminal 1)
python tooling/verify_openapi_{capability_id}_local_real.py

# Expected output: Provider starts, scenario PASS, provider terminates
```

#### Phase 2 Completion Gate 🚪

Before committing Phase 2:

```bash
# Terminal 1: Start provider
python tooling/openapi_providers/{capability_id}_service.py --port 8{781+N}

# Terminal 2: Run E2E verification
python tooling/verify_openapi_{capability_id}_local_real.py

# Expected: PASS

# Terminal 1: Verify no provider errors or warnings
# Terminal 2: Verify all OpenAPI suites still pass (without Phase 2 provider running)
python cli/main.py openapi verify-bindings --all
python tooling/verify_smoke_capabilities.py
python tooling/test_capability_contracts.py
```

Expected output: E2E passes, all existing suites still green ✅

#### Phase 2 Commit

```bash
git add \
  tooling/openapi_providers/{capability_id}_service.py \
  services/official/{capability_id}_openapi_local.yaml \
  services/official/specs/{capability_id}_openapi_local.yaml \
  bindings/official/{capability_id}/openapi_{capability_id_underscored}_local.yaml \
  tooling/openapi_scenarios_real/{capability_id}.openapi.local.json \
  tooling/verify_openapi_{capability_id}_local_real.py

git commit -m "openapi: integrate real service pilot for {capability_id}"
```

---

#### Capability Complete ✅

Mark in checklist above:
- Status: ✅ COMPLETE
- Mock Binding: ✅ PASS
- Real Service: ✅ PASS
- Commits: {commit_hash_phase1} {commit_hash_phase2}

Move to next capability.

---

## Per-Capability Port Allocation

Real services use auto-increment ports starting from 8780:

| Capability | Port | Service File |
|------------|------|--------------|
| data.schema.validate | 8780 | verify_openapi_data_schema_validate_local_real.py |
| text.summarize | 8781 | verify_openapi_text_summarize_local_real.py (pending) |
| code.execute | 8782 | verify_openapi_code_execute_local_real.py (pending) |
| web.fetch | 8783 | verify_openapi_web_fetch_local_real.py (pending) |
| pdf.read | 8784 | verify_openapi_pdf_read_local_real.py (pending) |
| audio.transcribe | 8785 | verify_openapi_audio_transcribe_local_real.py (pending) |
| fs.read | 8786 | verify_openapi_fs_read_local_real.py (pending) |
| agent.route | 8787 | verify_openapi_agent_route_local_real.py (pending) |

---

## Regression Test Matrix

After each commitment, verify matrix:

| Test | Command | Expected |
|------|---------|----------|
| Smoke Tests | `python tooling/verify_smoke_capabilities.py` | 8/8 PASS |
| Contract Tests | `python tooling/test_capability_contracts.py` | 33/33 PASS, 99 checks |
| OpenAPI Bindings (Mock) | `python cli/main.py openapi verify-bindings --all` | All mock scenarios PASS |
| OpenAPI Invoker | `python cli/main.py openapi verify-invoker` | 6/6 checks PASS |
| OpenAPI Error Contract | `python cli/main.py openapi verify-errors` | 7/7 checks PASS |
| Git Status | `git status --short` | (empty) |

If any test fails:
1. Revert last commit: `git revert HEAD --no-edit`
2. Diagnose issue using troubleshooting guide in OPENAPI_CONSTRUCTION_GUIDE.md
3. Fix and recommit with detailed message

---

## Troubleshooting

### Mock Scenario Fails with "Port already in use"

**Cause**: Previous mock server instance still running or port conflict

**Fix**:
```powershell
# Find process on port 8765
Get-NetTCPConnection -LocalPort 8765 | Select-Object OwnerProcess
taskkill /PID {pid} /F

# Or: Use different port in scenario mock_server.port
```

### Real Service E2E Fails with "Connection refused"

**Cause**: Provider process not started or health endpoint not implemented

**Fix**:
```bash
# Terminal 1: Start provider with verbose output
python -u tooling/openapi_providers/{capability_id}_service.py --host 127.0.0.1 --port 8{port}

# Terminal 2: Check port is listening
netstat -ano | findstr 8{port}

# Terminal 3: Test health endpoint manually
curl http://127.0.0.1:8{port}/health
```

### Binding Not Found During Scenario Execution

**Cause**: Binding file not in correct directory or binding_id mismatch

**Fix**:
```bash
# Verify binding exists:
ls -la bindings/official/{capability_id}/

# Verify binding id matches scenario binding_id field:
grep '"id"' services/official/{capability_id}_openapi_mock.yaml
grep '"binding_id"' tooling/openapi_scenarios/{capability_id}.openapi.mock.json

# Should match
```

### Scenario Output Doesn't Match Expected

**Cause**: Handler logic bug or service response format mismatch

**Fix**:
1. Compare actual output to expected_output in scenario JSON
2. Run provider with print statements to debug handler logic
3. Check OpenAPI spec response schema matches handler return value
4. Example:
   ```python
   # Handler must return JSON matching spec
   result = {"valid": True, "errors": []}
   self.wfile.write(json.dumps(result).encode())
   # Not: json.dumps([result])  ❌ Wrong format
   ```

---

## Population Phase Completion Gate ✅

Population phase closes when:

- [ ] All 8 smoke capabilities have mock binding + scenario
- [ ] All 8 capabilities have real service pilot + E2E verification
- [ ] All smoke tests pass (8/8 PASS)
- [ ] All contract tests pass (33/33 PASS)
- [ ] All OpenAPI scenarios pass (mock + real)
- [ ] All CLI commands pass (verify-bindings, verify-invoker, verify-errors)
- [ ] CI workflow passes (smoke.yml with openapi_verification job)
- [ ] No regressions detected
- [ ] All commits are reviewed and merged
- [ ] Documentation updated with lessons learned

---

## Success Criteria

Population phase is successful when:

1. **Completeness**: Every smoke capability has 3 binding paths (official, mock, real)
2. **Accessibility**: Each binding is copy-paste documented in OPENAPI_CONSTRUCTION_GUIDE.md
3. **Quality**: All tests green, no regressions, CI passing
4. **Operational**: Real service pilots demonstrate non-trivial business logic
5. **Maintainability**: Patterns consistent, naming conventions followed, documentation complete

---

## Next Steps (Phase 2 - Expansion)

After population phase complete:

1. **Extend to Full Registry**: Apply pattern to non-smoke capabilities
2. **Custom Protocol Support**: Add new protocol adapters (MCP, OpenRPC, gRPC)
3. **Provider Mesh**: Allow distributed multi-service deployments
4. **Performance Optimization**: Connection pooling, caching, batching
5. **Security Hardening**: TLS, authentication, rate limiting
6. **Multi-Cloud Ready**: AWS Lambda, Azure Functions, GCP Cloud Run providers

---

## Document Maintenance

This checklist should be updated:
- After each capability completion (mark status ✅)
- If new port allocations needed (add to table)
- If tooling command changes (update commands)
- If regression gates fail consistently (investigate root cause)

Last updated: 2026-03-11

# Target Architecture Merge Readiness (RFC-0007)

Status date: 2026-05-28
Reference RFC: docs/rfcs/RFC-0007-OSS-FIRST-TARGET-ARCH-EXECUTION.md
Progress baseline: docs/TARGET_ARCH_PROGRESS.md

## Executive Status

1. Overall strategic completion: 75%
2. Policy/Tenancy pillar: 88%
3. Tenant isolation matrix: passed (22/22)
4. same_tenant capability baseline: passed (5/5)

## RFC-0007 Contract Readiness

### 1) Scope classification

Status: Complete

Evidence:

1. docs/TARGET_ARCHITECTURE.md defines pattern transfer vs optional adapter vs operational substrate
2. docs/rfcs/RFC-0007-OSS-FIRST-TARGET-ARCH-EXECUTION.md enforces classification requirement

### 2) Invariant impact matrix

Status: Complete (documented), Partial (continuous enforcement)

Evidence:

1. docs/TARGET_ARCHITECTURE.md design invariants section
2. .github/PULL_REQUEST_TEMPLATE.md architecture-impact sections

Remaining:

1. Keep PR discipline consistent in all architecture-impacting changes

### 3) Backward compatibility and rollback

Status: Complete (for current policy/tenancy slice)

Evidence:

1. External policy modes off/shadow/enforce with fail-open/fail-closed controls
2. Runtime fallback behavior validated in runtime/test_safety.py

### 4) Validation evidence plan (local + CI alignment)

Status: Complete for policy/tenancy slice

Evidence:

1. tooling/verify_policy_shadow_mode.py
2. tooling/verify_tenant_isolation_matrix.py
3. runtime canary integration in .github/workflows/smoke.yml

### 5) Explicit non-goals

Status: Complete

Evidence:

1. docs/TARGET_ARCHITECTURE.md non-goals and scope guardrails
2. docs/rfcs/RFC-0007-OSS-FIRST-TARGET-ARCH-EXECUTION.md non-goals

## Slice-Specific Readiness (Policy/Tenancy)

### Runtime enforcement

Status: Complete

Evidence:

1. same_tenant enforcement in runtime execution pre-checks
2. tenant propagation through neutral API async/resume/replay/fork
3. transport propagation in HTTP and MCP paths

### Registry adoption baseline

Status: Complete

Capabilities currently enforcing same_tenant baseline:

1. capabilities/decision.task.delegate.yaml
2. capabilities/web.request.send.yaml
3. capabilities/email.message.send.yaml
4. capabilities/message.notification.send.yaml
5. capabilities/agent.plan.execute.yaml

### Test and verification

Status: Complete

Evidence:

1. runtime safety tests for same_tenant
2. policy shadow tests for same_tenant internal parity
3. channel tenancy probes (http-async/http-resume/http-replay)
4. transport tenancy probes (HTTP auth/body resolution + MCP skill.execute)

## Open Gaps Before Declaring Full Target Completion

1. Durability to Temporal-grade semantics (beyond current baseline contract)
2. Contracts/artifacts/promotion orchestration with stronger lineage model
3. OPA production policy bundle lifecycle and governance formalization
4. Wider same_tenant rollout beyond 5-capability baseline

## Commit Guidance with Large Dirty Trees

When there are many unrelated modified files, use selective commits by explicit pathspec and separate runtime vs registry commits.

Recommended split:

1. agent-skills commit: runtime, customer-facing, tooling, tests, docs in this slice
2. agent-skill-registry commit: capability YAML contract updates only
3. Exclude generated artifacts from both commits unless intentionally updated

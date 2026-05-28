# Policy Decision Contract (Shadow Mode v1)

Status: Active baseline
Last updated: 2026-05-28

This document defines the baseline policy decision contract used to introduce
external policy decision points safely, without changing current runtime safety behavior.

## Scope

Shadow mode v1 covers pre-execution policy decisions for:

1. trust_level checks
2. requires_confirmation checks

Gate execution behavior (`mandatory_pre_gates`, `mandatory_post_gates`) remains
runtime-owned in this stage and is out of scope for external parity.

## Contract Goals

1. Keep current runtime safety enforcement authoritative.
2. Evaluate optional external policy decisions in parallel.
3. Detect divergences before any enforcement handoff.

## Decision Input

Decision payload fields:

1. capability_id
2. step_id
3. safety (capability safety block)
4. context_trust_level
5. confirmed_capabilities
6. context_tenant_id (optional)
7. target_tenant_id (optional)

## Decision Output

Decision result fields:

1. status: `allow|block|require_human`
2. reason: optional string

## Shadow Mode Rules

1. Internal baseline decision remains source of truth.
2. External adapter decision is evaluated and compared, never enforced in v1.
3. Any mismatch is surfaced as verification failure for operator review.

same_tenant baseline rule:

1. If `allowed_targets` contains `same_tenant`, runtime requires a non-empty `context_tenant_id`.
2. If `target_tenant_id` is present and differs from `context_tenant_id`, policy blocks execution.
3. Current operational capability adoption baseline: `decision.task.delegate`, `web.request.send`, `email.message.send`, `message.notification.send`, `agent.plan.execute`.
4. Channel consistency probes validate tenant propagation across `http-async`, `http-resume`, and `http-replay` execution paths.
5. Transport consistency probes validate tenant sourcing across HTTP auth/body resolution and MCP `skill.execute` invocation.

## Runtime Operating Modes

The runtime supports three policy externalization modes:

1. `off` (default): external adapter not used.
2. `shadow`: compare external decision vs internal baseline, internal remains authoritative.
3. `enforce`: enforce external decision for pre-checks (`trust_level`, `requires_confirmation`) with internal fallback behavior controlled by fail-open/fail-closed.

Environment controls:

1. `AGENT_SKILLS_POLICY_EXTERNAL_MODE=off|shadow|enforce`
2. `AGENT_SKILLS_POLICY_EXTERNAL_FAIL_OPEN=true|false`
3. `AGENT_SKILLS_POLICY_EXTERNAL_ADAPTER=none|mirror|opa`
4. `AGENT_SKILLS_POLICY_OPA_URL=http://<opa-host>/v1/data/orca/policy/pre`
5. `AGENT_SKILLS_POLICY_OPA_TIMEOUT_SECONDS=<float>`

Fail-open behavior:

1. If external adapter is unavailable and fail-open is enabled, runtime falls back to internal baseline checks.
2. If fail-open is disabled, external adapter errors become runtime policy execution failures.

## Suggested Rollout Profile

1. Dev: `MODE=shadow`, `ADAPTER=mirror` or `ADAPTER=opa`, `FAIL_OPEN=true`
2. Staging: `MODE=shadow`, `ADAPTER=opa`, `FAIL_OPEN=true`
3. Production initial: `MODE=enforce`, `ADAPTER=opa`, `FAIL_OPEN=true`
4. Production hardened: `MODE=enforce`, `ADAPTER=opa`, `FAIL_OPEN=false`

## Verification

Run:

```bash
python tooling/verify_policy_shadow_mode.py --report-file artifacts/policy_shadow_report.json
```

Tenant isolation matrix:

```bash
python tooling/verify_tenant_isolation_matrix.py --report-file artifacts/tenant_isolation_matrix_report.json
```

OPA policy bundle lifecycle:

```bash
python tooling/verify_policy_bundle_lifecycle.py --bundle-root policies/opa --report-file artifacts/policy_bundle_lifecycle_report.json
```

Report:

1. status
2. summary.total/matched/mismatched/match_ratio
3. comparisons[]
4. mismatches[]

Tenant matrix report:

1. status
2. summary.total/passed/failed/pass_ratio
3. by_surface (runtime_identity, runtime_persistence, runtime_policy, channel_tenancy, transport_tenancy, registry_vocabulary, registry_capabilities)
4. checks[]

Policy bundle lifecycle report:

1. status
2. summary.total/passed/failed/pass_ratio
3. bundle_root
4. checks[]
5. contract (`opa_policy_bundle_lifecycle_v2`)

## Out of Scope (v1)

1. OPA runtime decision enforcement cutover.
2. Replacing in-runtime safety gates.
3. Tenant-scoped policy-bundle governance with explicit environment promotion controls.

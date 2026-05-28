# OPA Policy Bundle Lifecycle (v2)

Status: Active baseline
Last updated: 2026-05-28

This document defines a minimal, auditable lifecycle contract for OPA policy
bundles used by external policy decision rollout.

## Scope

This lifecycle covers bundle structure and compatibility checks for the pre-decision path:

1. `/v1/data/orca/policy/pre`
2. package `orca.policy.pre`

Runtime safety remains authoritative during staged rollout.

## Bundle Layout

Expected files under `policies/opa`:

1. `bundle_manifest.json`
2. `policy_pre.rego`

## Manifest Contract

`bundle_manifest.json` must contain:

1. `bundle_name`
2. `bundle_version`
3. `policy_package` (must be `orca.policy.pre`)
4. `decision_path` (must be `/v1/data/orca/policy/pre`)
5. `compatibility` block
6. `tenant_scope` block
7. `promotion_policy` block

Required governance fields:

1. `tenant_scope.mode` in `{shared_with_tenant_constraints, tenant_scoped}`
2. `tenant_scope.tenant_selection = context_tenant_only`
3. `tenant_scope.cross_tenant_allowed = false`
4. `promotion_policy.required_reviews >= 1`
5. `promotion_policy.enforce_requires_shadow_validation = true`
6. `promotion_policy.require_bundle_version_bump = true`
7. `promotion_policy.environment_promotion.sequence = [dev, staging, prod]`
8. `promotion_policy.environment_promotion.rules.dev_to_staging.require_shadow_parity = true`
9. `promotion_policy.environment_promotion.rules.dev_to_staging.min_runtime_canary_pass_ratio >= 1.0`
10. `promotion_policy.environment_promotion.rules.staging_to_prod.require_shadow_parity = true`
11. `promotion_policy.environment_promotion.rules.staging_to_prod.min_runtime_canary_pass_ratio >= 1.0`
12. `promotion_policy.environment_promotion.rules.staging_to_prod.required_approvals >= 2`

## Rego Contract

`policy_pre.rego` must contain:

1. `package orca.policy.pre`
2. `default result` decision baseline

## Verification

Run:

```bash
python tooling/verify_policy_bundle_lifecycle.py --bundle-root policies/opa --report-file artifacts/policy_bundle_lifecycle_report.json
```

Report fields:

1. status
2. summary.total/passed/failed/pass_ratio
3. checks[]
4. contract (`opa_policy_bundle_lifecycle_v2`)

## Rollout Intention

1. Keep bundle checks in CI as a readiness gate.
2. Expand decision coverage over time without breaking runtime-safe defaults.
3. Enforce explicit environment promotion controls before production-enforce cutover.

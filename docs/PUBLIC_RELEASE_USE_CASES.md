# Public Release Use Cases

Status: active
Last updated: 2026-05-28

This document defines the minimum use cases that must be clearly understood,
validated, and evidenced before a public release.

## 1. Purpose

Use this catalog to answer one question: "Are we truly ready to expose this
publicly without ambiguity?"

A release candidate is considered clear and publishable only when each required
use case below has:

1. A concrete execution path
2. A measurable acceptance criterion
3. Attached evidence (artifact/report/log)

## 2. Required Use Cases Before Public Launch

### UC-01: Basic capability execution path

Goal:

1. A representative skill executes end-to-end with expected output mapping.

How to validate:

1. Run smoke and capability contract checks.
2. Run at least one real skill execution with trace correlation.

Acceptance criteria:

1. Smoke verification passes.
2. Contract validation passes.
3. Skill returns expected required outputs with no mapping errors.

Evidence:

1. `artifacts/smoke_report.json`
2. Contract test output from `tooling/test_capability_contracts.py`
3. Execution trace/log with trace id

### UC-02: Registry-governed consistency and freshness

Goal:

1. Registry is valid and catalog artifacts are fresh (no drift).

How to validate:

1. Run the full registry CI-equivalent sequence.

Acceptance criteria:

1. All registry governance scripts pass.
2. No catalog freshness drift remains after generation.

Evidence:

1. Outputs from:
   - `tools/validate_registry.py`
   - `tools/governance_guardrails.py`
   - `tools/capability_governance_guardrails.py`
   - `tools/enforce_capability_sunset.py`
   - `tools/generate_catalog.py`
   - `tools/registry_stats.py`

### UC-03: Policy bundle lifecycle governance

Goal:

1. OPA bundle manifest and rego contract remain valid and promotion-safe.

How to validate:

1. Run lifecycle verifier and schema checks through CI governance gate.

Acceptance criteria:

1. Lifecycle report status is `passed`.
2. No manifest schema conformance failures.
3. Tenant scope and promotion policy checks pass.

Evidence:

1. `artifacts/policy_bundle_lifecycle_report.json`
2. `artifacts/policy_gate_freshness_report.json`

### UC-04: Runtime canary safety controls

Goal:

1. Runtime safety remains intact under canary checks.

How to validate:

1. Run runtime canary suite including durability, policy shadow, and tenant matrix.

Acceptance criteria:

1. Runtime canary job passes.
2. Durability, shadow parity, and tenant isolation reports pass.

Evidence:

1. `artifacts/durability_contract_report.json`
2. `artifacts/policy_shadow_report.json`
3. `artifacts/tenant_isolation_matrix_report.json`

### UC-05: Promotion-readiness decision path

Goal:

1. Promotion decisions are explicit and evidence-based for `dev -> staging -> prod`.

How to validate:

1. Generate and verify policy promotion readiness reports.

Acceptance criteria:

1. Promotion readiness report status is `passed`.
2. Verification report status is `passed`.
3. `dev_to_staging.ready` and `staging_to_prod.automated_ready` are true.

Evidence:

1. `artifacts/policy_promotion_readiness_report.json`
2. `artifacts/policy_promotion_readiness_verify_report.json`

### UC-06: Branch protection operational closure

Goal:

1. Public release branch is effectively protected in GitHub.

How to validate:

1. Apply/verify ruleset using GitHub UI runbook.
2. Run branch protection verifiers.

Acceptance criteria:

1. Required checks match canonical file.
2. PR review and conversation safeguards are active.
3. Bypass scope is minimal and reviewed.

Evidence:

1. `artifacts/branch_protection_policy_report.json`
2. `artifacts/required_status_checks_consistency_report.json`
3. `artifacts/github_branch_protection_report.json` or manual UI proof when `unverified`

### UC-07: Workflow integrity against regressions

Goal:

1. CI workflow embedded Python snippets are syntactically safe.

How to validate:

1. Run embedded-workflow Python verifier.

Acceptance criteria:

1. Embedded Python report status is `passed`.

Evidence:

1. `artifacts/workflow_embedded_python_report.json`

### UC-08: Stability trend for critical jobs

Goal:

1. Critical CI jobs show acceptable pass-rate trend before public exposure.

How to validate:

1. Generate trend report and evaluate trend SLO report.

Acceptance criteria:

1. Trend report is generated.
2. SLO evaluation has no blocking breaches for configured policy.

Evidence:

1. `artifacts/critical_ci_trend_report.json`
2. `artifacts/critical_ci_trend_slo_report.json`

### UC-09: Consolidated governance readability

Goal:

1. Release decision can be made from executive summaries without digging into all raw files.

How to validate:

1. Generate executive summary artifacts in CI governance and runtime canary jobs.

Acceptance criteria:

1. Executive summary artifacts exist and are readable.
2. Status is not `failed`.

Evidence:

1. `artifacts/governance_executive_summary.json`
2. `artifacts/runtime_governance_executive_summary.json`
3. `artifacts/release_readiness_gate_report.json`

### UC-10: Operator readiness for incidents

Goal:

1. Team can react quickly to regression after release.

How to validate:

1. Verify incident triggers and first-response steps are documented.

Acceptance criteria:

1. Incident triggers and immediate actions are clear and linked.

Evidence:

1. `docs/PRODUCTION_READINESS.md` incident section
2. `docs/TROUBLESHOOTING.md` and related runbooks

## 3. Public Launch Decision Matrix

Release decision:

1. Go:
   - All required use cases accepted.
   - No `failed` governance summaries.
   - Any `unverified` is only the allowed branch-protection visibility case with manual evidence.
2. No-Go:
   - Any required use case missing evidence.
   - Any policy/runtime governance control failed.
   - Any unverified outside the allowed exception rule.

## 4. Suggested Release Evidence Package

Attach this package to release notes/PR:

1. CI run URL(s) for `policy-bundle-governance`, `runtime_canary`, `ci_stability_trend`, and `dx_metrics`
2. Governance executive summary artifacts
3. Runtime governance executive summary artifacts
4. Release readiness gate artifact
5. Registry validation sequence output
6. Branch protection verification evidence (API report or UI proof)

## 5. Cross References

1. `docs/PRODUCTION_READINESS.md`
2. `docs/CI_AND_TESTING.md`
3. `docs/GITHUB_RULESET_RUNBOOK.md`
4. `docs/OPA_POLICY_BUNDLE_LIFECYCLE.md`
5. `docs/PRODUCT_100_EXECUTION_PLAN.md`

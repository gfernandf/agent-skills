# Public Release Use Cases

Status: active
Last updated: 2026-05-28

This document defines the minimum use cases that must be clearly understood,
validated, and evidenced before a public release.

## 1. Purpose

Use this catalog to answer one question: "Are we truly ready to expose this
publicly without ambiguity?"

Why this catalog is useful now:

1. It turns readiness into evidence, so the team can prove progress instead of debating it.
2. It keeps the release bar explicit, which reduces last-minute guesswork.
3. It separates durable repo-backed proof from manual operational checks, which makes the process honest and auditable.
4. It gives reviewers a single narrative for why the current system is safer and more repeatable than an ad hoc release process.

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
3. Replay determinism report passes with complete repeated execution set.
4. Workflow version compatibility report passes with full execution set and no failed tests.
5. Checkpoint schema/provenance report passes with full execution set and no failed tests.
6. Provenance coverage report passes with full execution set and no failed tests.

Evidence:

1. `artifacts/durability_contract_report.json`
2. `artifacts/policy_shadow_report.json`
3. `artifacts/tenant_isolation_matrix_report.json`
4. `artifacts/durability_advanced_report.json`
5. `artifacts/replay_determinism_report.json`
6. `artifacts/workflow_version_compatibility_report.json`
7. `artifacts/checkpoint_schema_provenance_report.json`
8. `artifacts/provenance_coverage_report.json`

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

1. The repository's public release branch is effectively protected in GitHub.

Why this matters:

1. Governance closes the gap between code state and release authority.
2. Required checks and review rules protect the release path from accidental bypass.
3. The manual UI proof path acknowledges that some controls live outside the repo while still keeping the evidence package complete.

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

## 4. Why This Release Model Is Stronger

The current model is intentionally stricter than a typical "works on my machine" or
"push and hope" release process. It is stronger because:

1. Every release claim is backed by concrete artifacts, not just tribal knowledge.
2. Runtime safety, governance, and promotion readiness are checked independently.
3. Evidence is reusable across release decisions, so the same work supports multiple gates.
4. Operators can understand the release state quickly from the reports without reverse engineering the system.

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
4. `artifacts/release_lineage.json`

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
5. Release lineage artifact
6. Registry validation sequence output
7. Branch protection verification evidence (API report or UI proof)

## 5. Cross References

1. `docs/PRODUCTION_READINESS.md`
2. `docs/CI_AND_TESTING.md`
3. `docs/GITHUB_RULESET_RUNBOOK.md`
4. `docs/OPA_POLICY_BUNDLE_LIFECYCLE.md`
5. `docs/PRODUCT_100_EXECUTION_PLAN.md`
6. `docs/RELEASE_LINEAGE_MODEL.md`

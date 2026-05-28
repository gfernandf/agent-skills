# Production Readiness Playbook

Status: active
Last updated: 2026-05-28

This playbook defines the minimum controls, evidence, and operational checks
required to treat the current governance stack as production-ready.

## 1. Scope

Applies to:

1. Policy bundle governance and lifecycle checks
2. Runtime canary safety and promotion-readiness evidence
3. Branch protection and required-check operational controls
4. Critical CI stability trend and SLO tracking
5. Registry freshness and governance sequence

## 2. Production Go/No-Go Criteria

A release candidate is **Go** only when all required controls below are satisfied.

### 2.1 Required CI outcomes

1. `policy-bundle-governance` job: passed
2. `runtime_canary` job: passed
3. `dx_metrics` job: passed
4. `ci_stability_trend` job: completes and publishes trend + SLO artifacts

### 2.2 Required governance artifact statuses

1. `artifacts/policy_bundle_lifecycle_report.json`: `status = passed`
2. `artifacts/policy_gate_freshness_report.json`: `status = passed`
3. `artifacts/branch_protection_policy_report.json`: `status = passed`
4. `artifacts/required_status_checks_consistency_report.json`: `status = passed`
5. `artifacts/workflow_embedded_python_report.json`: `status = passed`
6. `artifacts/policy_promotion_readiness_report.json`: `status = passed`
7. `artifacts/policy_promotion_readiness_verify_report.json`: `status = passed`

### 2.3 Executive summary acceptance

1. `artifacts/governance_executive_summary.json` must be present
2. `artifacts/runtime_governance_executive_summary.json` must be present
3. Consolidated status interpretation:
   - `passed`: acceptable
   - `unverified`: acceptable only for controls that are operationally external to repo code
   - `failed`: not acceptable

### 2.4 Allowed exception window (`unverified`)

`unverified` is allowed only when all are true:

1. The affected control is `github_branch_protection_report`
2. A manual GitHub UI verification was performed using `docs/GITHUB_RULESET_RUNBOOK.md`
3. Verification evidence is attached to the release/PR notes
4. No other governance report is failed

If any other control is `unverified`, treat as **No-Go** until resolved.

## 3. Mandatory Local Validation Before Promotion

### 3.1 agent-skills

```bash
cd agent-skills
pip install -e ".[dev]"
python tooling/verify_policy_bundle_lifecycle.py --bundle-root policies/opa --report-file artifacts/policy_bundle_lifecycle_report.json
python tooling/verify_policy_gate_freshness.py --report-file artifacts/policy_gate_freshness_report.json
python tooling/verify_branch_protection_policy.py --report-file artifacts/branch_protection_policy_report.json
python tooling/verify_required_status_checks_consistency.py --report-file artifacts/required_status_checks_consistency_report.json
python tooling/verify_workflow_embedded_python.py --report-file artifacts/workflow_embedded_python_report.json
```

### 3.2 agent-skill-registry (CI-equivalent sequence)

```bash
cd agent-skill-registry
python tools/validate_registry.py
python tools/governance_guardrails.py --fail-on-high-risk-overlap-channels community,official
python tools/capability_governance_guardrails.py
python tools/enforce_capability_sunset.py
python tools/generate_catalog.py
python tools/registry_stats.py
```

## 4. Release Evidence Bundle

Attach at least:

1. CI run URL
2. `policy-bundle-governance-report` artifact
3. `runtime-canary-report` artifact
4. `critical-ci-trend-report` artifact
5. If applicable, screenshot/export of GitHub ruleset settings for target branch

## 5. Incident Response Triggers

Treat as production incident when any of the following occurs on default branch:

1. `runtime_canary` fails
2. `policy-bundle-governance` fails
3. Governance executive summary status is `failed`
4. Critical CI trend SLO starts reporting repeated breaches across critical jobs

Immediate actions:

1. Freeze non-essential merges
2. Identify first failing control from executive summary artifact
3. Apply fix and re-run affected workflow(s)
4. Document cause and corrective action in PR/release notes

## 6. Ownership

1. Code-level governance contracts: repository maintainers
2. GitHub operational controls (rulesets/branch protection): repository admins
3. Promotion decision authority: release owner + approver(s)

## 7. Related Documents

1. `docs/CI_AND_TESTING.md`
2. `docs/OPA_POLICY_BUNDLE_LIFECYCLE.md`
3. `docs/BRANCH_PROTECTION_POLICY.md`
4. `docs/GITHUB_RULESET_RUNBOOK.md`
5. `docs/PUBLIC_RELEASE_USE_CASES.md`

## 8. Clarification: What "External Operational Closure" Means

When we say this gap is external to repository code, it means:

1. The repository can verify expectations and detect drift.
2. The repository cannot force GitHub tenant-level settings by itself.
3. A repository admin must apply branch rules/rulesets in GitHub settings UI.

Why this matters:

1. CI can pass while push/merge governance is still weak if rulesets are not correctly applied.
2. This is the reason API-based verification may return `unverified` under limited token permissions.

Minimum acceptance checklist for closure:

1. Ruleset/branch protection is active on the release branch.
2. Required checks match `docs/required_status_checks.json` exactly.
3. PR review, stale review dismissal, and conversation resolution are enabled.
4. Bypass list is restricted and explicitly reviewed.
5. Evidence is attached in PR/release notes (report + UI proof).

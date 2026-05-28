# GitHub Ruleset Runbook (Main/Master)

Status: operational closure guide
Last updated: 2026-05-28

This runbook closes the remaining gap that cannot be enforced purely from repository code:
GitHub branch protection/ruleset settings for `main` and `master`.

## 1. Prerequisites

1. Admin or maintainer access to repository settings.
2. Required checks source of truth:
   `docs/required_status_checks.json`
3. Policy reference:
   `docs/BRANCH_PROTECTION_POLICY.md`

## 2. Configure Ruleset (Recommended)

Path in GitHub UI:

1. Repository -> Settings -> Rules -> Rulesets
2. New ruleset -> Branch ruleset

Target branches:

1. `main`
2. `master`

Enable rules:

1. Require a pull request before merging
2. Require approvals: at least 1
3. Dismiss stale pull request approvals when new commits are pushed
4. Require conversation resolution before merging
5. Require status checks to pass
6. Restrict force pushes
7. Restrict deletions

Required status checks (exact names):

1. `cognitive-quality-gates`
2. `policy-bundle-governance`
3. `runtime_canary`

Bypass control:

1. Keep bypass list minimal (prefer admin-only)
2. Do not allow broad team bypass for routine pushes

## 3. If Using Legacy Branch Protection Instead of Rulesets

Path in GitHub UI:

1. Repository -> Settings -> Branches -> Branch protection rules

Create/update rules for `main` and `master` with the same controls and required checks listed above.

## 4. Verify Operationally

After saving settings, verify with in-repo tooling.

Local manual check (may be `unverified` without token permissions):

```bash
python tooling/verify_github_branch_protection.py --report-file artifacts/github_branch_protection_report.json
```

CI governance check:

1. `policy-bundle-governance` in `.github/workflows/ci.yml` runs:
   `tooling/verify_github_branch_protection.py`
2. Report artifact:
   `artifacts/github_branch_protection_report.json`

Interpretation:

1. `status = passed`: settings verified by API and required checks found
2. `status = unverified`: token/permission limitation; use admin token or manual UI confirmation
3. `status = failed`: configuration mismatch that must be fixed

## 5. Change Management Rule

Any change to required checks must update all of:

1. `docs/required_status_checks.json`
2. `docs/BRANCH_PROTECTION_POLICY.md`
3. GitHub ruleset/branch-protection required checks list

Then validate:

```bash
python tooling/verify_required_status_checks_consistency.py
python tooling/verify_branch_protection_policy.py
```

## 6. Audit Checklist (Production Promotion)

Before marking a promotion as Go, confirm and record:

1. Default branch ruleset/branch protection is enabled
2. Required status checks exactly match `docs/required_status_checks.json`
3. PR review requirements are enabled (minimum approvals and stale review dismissal)
4. Force push/deletion restrictions are enabled
5. Bypass list is explicitly reviewed and limited
6. `tooling/verify_github_branch_protection.py` report captured

Evidence to attach in PR/release notes:

1. `artifacts/github_branch_protection_report.json`
2. link or screenshot of GitHub ruleset configuration
3. last successful run IDs for `policy-bundle-governance` and `runtime_canary`

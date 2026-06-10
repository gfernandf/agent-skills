# Continuous Governance Validation

Status: active operational runbook
Last updated: 2026-06-10

This document describes the automated continuous validation workflow that runs daily
to detect governance drift before it causes issues in CI or release gates.

## Overview

The workflow `governance_continuous_validation.yml` executes every day at 00:00 UTC
to validate that critical governance settings remain consistent and operational.

## Checks Performed

### 1. GitHub Branch Protection Verification

**What it checks**: Verifies that the default branch (`master`) is protected with
required status checks and PR review requirements.

**File**: `tooling/verify_github_branch_protection.py`
**Report**: `governance_branch_protection_check.json`

Status meanings:
- `passed`: All required checks present and enforced.
- `failed`: Configuration mismatch (e.g., missing required status checks).
- `unverified`: Cannot verify due to API permissions (non-blocking if ruleset is manual).

**Remediation if failed**:
1. Review `docs/GITHUB_RULESET_RUNBOOK.md` for current requirements.
2. Verify GitHub ruleset or branch protection settings match required checks:
   - `cognitive-quality-gates`
   - `policy-bundle-governance`
   - `runtime_canary`
3. Confirm ruleset `enforcement` is set to `active`, not `disabled`.

### 2. Critical CI Trend Report

**What it checks**: Collects pass rates of critical jobs over the last 20 runs.

**Files**:
- `tooling/report_critical_ci_trend.py` → `governance_trend_report.json`
- `tooling/evaluate_critical_ci_trend.py` → `governance_trend_slo_report.json`

Status meanings:
- `passed`: Trend report generated with sufficient samples.
- `unverified`: Unable to fetch job data (e.g., API auth issue, rate limit).

**Remediation if unverified**:
1. Check GitHub CLI authentication: `gh auth status`
2. Verify `GITHUB_TOKEN` in workflow has `workflow` scope.
3. If rate-limited, wait 1 hour and re-run manually.

### 3. Critical CI Trend SLO Evaluation

**What it checks**: Evaluates if collected trend data meets minimum pass rate (0.80)
and minimum sample count (5) thresholds.

**Status meanings**:
- `pass`: All jobs meet SLO thresholds.
- `breach`: One or more jobs fall below pass rate threshold.
- `unverified`: Cannot evaluate (e.g., insufficient samples).

**Remediation if breach**:
1. Run `gh run list --workflow=smoke.yml --limit 5` to see recent runs.
2. Identify which job is failing repeatedly.
3. File or check existing GitHub issue in the repository.
4. If consistent failure, escalate to maintainers; if transient, wait for next run.

### 4. Required Status Checks Consistency

**What it checks**: Verifies that `docs/required_status_checks.json` matches
definitions in workflows and policy documents.

**File**: `tooling/verify_required_status_checks_consistency.py`
**Report**: `governance_status_checks_consistency.json`

Status meanings:
- `passed`: All required checks are consistently defined.
- `failed`: Mismatch between JSON, workflows, or policies.

**Remediation if failed**:
1. Review changes to `docs/required_status_checks.json`.
2. Verify all three checks are present in `.github/workflows/ci.yml` and `smoke.yml`.
3. Verify policy file `.github/release_gate_policy.json` lists the same checks.
4. Update all three sources if any were out of sync.

### 5. Release Gate Policy Configuration

**What it checks**: Verifies that `.github/release_gate_policy.json` is well-formed
and contains all expected profiles with required fields.

**File**: `tooling/verify_release_gate_policy.py`
**Report**: `governance_release_gate_policy.json`

Status meanings:
- `passed`: Policy file has all three profiles (strict, transitional, promotion) with required fields.
- `failed`: Missing profiles, fields, or type mismatches in policy configuration.

**Remediation if failed**:
1. Review `.github/release_gate_policy.json` for syntax errors or missing profiles.
2. Ensure each profile has: `allow_trend_unverified`, `max_high_failures`, `max_medium_failures`.
3. Verify no unexpected fields were added or profiles deleted.
4. Validate JSON format: `python -m json.tool .github/release_gate_policy.json`

## Overall Validation Report

**File**: `governance_continuous_validation_report.json`

This is a compiled summary of all checks:
- `overall_status`: `passed` if all checks pass, `failed` otherwise.
- `governance_checks`: Dictionary with status of each individual check.

## Alerting and Escalation

### Automatic Issue Creation

When the workflow detects failed checks, it automatically creates a GitHub issue with:
- **Title**: `❌ Governance Validation Failed - [Check Name]`
- **Labels**: `governance`, `validation`, `automated`
- **Body**: Pre-populated with check details, links to runbook, and remediation steps
- **Smart Deduplication**: If an issue already exists from today, adds a comment instead of creating duplicates

### Issue Lifecycle

1. **Issue Created**: When first check fails on a given day
2. **Updates**: Subsequent failures on the same day add comments to the same issue
3. **Resolution**: Issue is manually closed once remediation is confirmed passing
4. **Archival**: Closed issues remain in the repository for audit trail

### Watching Governance Issues

To receive real-time notifications:

```bash
# Subscribe to governance validation issues
gh issue list --label governance,validation,automated --state open
```

Or configure GitHub notifications:
1. Go to repository Settings → Notifications
2. Create custom filter for `governance` + `validation` labels
3. Select your notification channel (email, GitHub notifications, etc.)

## Responding to Failures

### Daily monitoring

1. Check the workflow summary at:
   `https://github.com/gfernandf/agent-skills/actions/workflows/governance_continuous_validation.yml`

2. If `overall_status` is `failed`:
   - GitHub issue will be automatically created
   - Review individual check failures
   - Follow remediation steps for the failing check(s)
   - Do NOT ignore; address within 24 hours to prevent promotion gate issues

3. After remediation:
   - Manually re-run: `gh workflow run governance_continuous_validation.yml`
   - Confirm validation passes
   - Close the GitHub issue

### Manual re-run

If you make configuration changes (e.g., branch protection), re-run the validation:

```bash
gh workflow run governance_continuous_validation.yml --repo gfernandf/agent-skills
```

Or via GitHub UI:
1. Go to Actions → Governance Continuous Validation
2. Click "Run workflow" → "Run workflow" (uses default branch)

### Disabling/Modifying the Schedule

Edit `.github/workflows/governance_continuous_validation.yml`:
- Change `cron` schedule line to adjust frequency.
- Add/remove checks as needed in the workflow steps.
- Rebuild validation report logic in the "Compile continuous validation report" step.

## Related

1. `docs/BRANCH_PROTECTION_POLICY.md`
2. `docs/GITHUB_RULESET_RUNBOOK.md`
3. `docs/required_status_checks.json`
4. `tooling/verify_github_branch_protection.py`
5. `tooling/report_critical_ci_trend.py`

# SLO Hardening Roadmap - Progressive Threshold Enforcement

## Current State (Phase 1 - Baseline)
- **DX_SLO_ENFORCE**: false (disabled)
- **DX_SLO_MAX_TTFS_SECONDS**: 300
- **DX_SLO_MIN_DOCS_PARITY**: 0.90
- **DX_SLO_MIN_CHECK_PASS_RATIO**: 1.00
- **CI_TREND_SLO_ENFORCE**: true (enabled)
- **CI_TREND_SLO_MIN_PASS_RATE**: 0.80 (very conservative)
- **CI_TREND_SLO_MIN_SAMPLES**: 5
- **Enforcement Mode**: Collect metrics only, soft reporting

**Rationale**: Establish baseline metrics collection and validation without blocking PRs/releases.

---

## Phase 2 - Warning Level (2026-06-11)
**Target**: Enable DX SLO enforcement; increase CI trend pass rate threshold to warning level.

### Changes
- **DX_SLO_ENFORCE**: `true` (enable DX metrics SLO)
- **CI_TREND_SLO_MIN_PASS_RATE**: 0.85 (from 0.80)
- **Enforcement Mode**: CI trend violations create GitHub issues (alerting only)

### Metrics Affected
- DX metrics now fail fast if docs parity < 90% or TTFS > 300s
- CI trend failures if pass rate < 85% over last 20 runs
- GitHub issue creation on threshold breach (non-blocking to merge)

### Expected Impact
- Alert team to DX regression early (before hard SLO breach)
- Identify CI stability drift before critical failure
- ~2-3 issues/week expected as baseline stabilizes

**Deployment**: Commit to master, effective 2026-06-11

---

## Phase 3 - Soft Fail (2026-06-25, ~2 weeks)
**Target**: Increase pass rate threshold; tighten DX metrics conservatively.

### Planned Changes
- **CI_TREND_SLO_MIN_PASS_RATE**: 0.90 (from 0.85)
- **DX_SLO_MAX_TTFS_SECONDS**: 280 (from 300)
- **DX_SLO_MIN_DOCS_PARITY**: 0.92 (from 0.90)
- **Enforcement Mode**: Non-blocking failure signal (issue creation, but PR merge allowed)

### Rationale
- Post-stabilization from Phase 2; CI should be consistently >85% by then
- DX metrics tightened moderately to catch regression earlier

---

## Phase 4 - Hard Fail (2026-07-09, ~4 weeks)
**Target**: Strict enforcement; block PRs on SLO breach.

### Planned Changes
- **CI_TREND_SLO_MIN_PASS_RATE**: 0.95 (from 0.90)
- **DX_SLO_MAX_TTFS_SECONDS**: 250 (from 280)
- **DX_SLO_MIN_DOCS_PARITY**: 0.95 (from 0.92)
- **CI_TREND_SLO_FAIL_ON_UNVERIFIED**: true (already enabled, will hard-fail)
- **Enforcement Mode**: Blocking - PR check fails, release gated

### Rationale
- By Phase 4, metrics should be predictably stable >95%
- Hard fail protects trunk from unpredictable flakes
- Release gates also enforced by release_readiness_gate job

---

## Monitoring & Adjustment
- Track SLO violations per phase in GitHub issues + artifacts
- Adjust timelines if stabilization takes longer (e.g., if Phase 2 sees >10 issues/week)
- Document exceptions/waivers in release notes if hard failures occur

## Rollback Plan
- Each phase is reversible by simply adjusting env vars in smoke.yml
- If Phase N introduces too much noise, retreat to Phase N-1 for 1 more week
- Alert issue will be created if breaches occur for visibility

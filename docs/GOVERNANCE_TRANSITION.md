# Governance Transition Plan

> From single-author to community-governed project.

## Current State (Phase 0)

- Single maintainer with full commit access
- All decisions documented in ADRs and design docs
- Automated CI gates enforce quality (lint, tests, binding contracts, security)
- Registry governance tooling enforces vocabulary, overlap, and sunset policies
- No external contributors yet

## Trigger: When to Activate

The governance model upgrades when **any** of these thresholds is met:

| Trigger | Threshold |
|---------|-----------|
| Active contributors (≥1 merged PR in 90 days) | ≥ 3 |
| External organizations using the project | ≥ 2 |
| Published skills from non-maintainer authors | ≥ 5 |

Until a trigger fires, the single maintainer operates under the rules
below but without forming a committee.

## Phase 1 — Lightweight Governance (3–5 contributors)

### Roles

| Role | Permissions | How to earn |
|------|------------|-------------|
| **Contributor** | Open PRs, comment on issues | First merged PR |
| **Reviewer** | Approve PRs in assigned areas | 5 merged PRs + maintainer nomination |
| **Maintainer** | Merge PRs, release, triage | Reviewer for 3 months + existing maintainer vote |

### Decision process

- **Routine changes** (bug fixes, docs, new community skills): single reviewer approval + CI green.
- **Significant changes** (new capability domain, breaking contract change, new binding protocol): RFC issue open for 7 days, at least 2 maintainer approvals.
- **Governance changes** (role model, CI policy, admission policy): RFC issue open for 14 days, unanimous maintainer approval.

### RFC process

1. Open a GitHub issue with title `RFC: <short description>`.
2. Use the RFC template (label `rfc`).
3. Discussion period: minimum 7 days.
4. Decision recorded in the issue and linked ADR.

### Release process

- Any maintainer can cut a release.
- CHANGELOG.md must be updated before tagging.
- CI must be green on the release commit.

## Phase 2 — Steering Committee (≥6 active contributors)

### Formation

- 3-seat steering committee elected by active contributors.
- Term: 6 months, staggered (1 seat rotates every 2 months).
- Election: simple majority of active contributors (≥1 merged PR in 90 days).

### Committee responsibilities

- Approve/reject RFCs for breaking changes.
- Resolve disputes between maintainers.
- Set release cadence and roadmap priorities.
- Manage security disclosures.

### Voting rules

- Quorum: 2 of 3 members.
- Simple majority for standard decisions.
- Unanimous for governance model changes.
- Votes recorded in GitHub Discussions.

## Phase 3 — Foundation (stretch)

When the project reaches ≥20 active contributors or multi-organization
adoption, evaluate moving to a foundation model:

- CNCF sandbox / Linux Foundation project
- Formal trademark policy
- Independent CI/CD infrastructure
- Dedicated security response team

## Contributor Ladder

```
Contributor → Reviewer → Maintainer → Steering Committee Member
     ↑            ↑           ↑                ↑
  1 merged PR   5 PRs     3 months          Election
                + nomination  + vote
```

## Code Ownership (CODEOWNERS)

When Phase 1 activates, create `.github/CODEOWNERS`:

```
# Default
*                       @lead-maintainer

# Runtime core
runtime/                @lead-maintainer
gateway/                @lead-maintainer

# SDK and adapters
sdk/                    @sdk-reviewers
official_mcp_servers/   @sdk-reviewers

# Registry governance
policies/               @lead-maintainer
```

## Security Disclosure

- Private vulnerability reports via GitHub Security Advisories.
- Maintainers acknowledge within 48 hours.
- Patches released within 14 days of confirmed vulnerability.
- Public disclosure after patch is available.

## Compatibility Guarantee

Once Phase 1 activates:

- Capability contracts are **never** broken without a deprecation cycle
  (see `CAPABILITY_SUNSET_POLICY.md` — minimum 90-day window).
- SDK public APIs follow semver.
- OpenAPI spec changes require backward compatibility or a new version prefix.

## Related Documents

- [SKILL_GOVERNANCE_MANIFESTO.md](SKILL_GOVERNANCE_MANIFESTO.md) — Product-level trust model
- [CONTRIBUTING.md](../CONTRIBUTING.md) — Current contribution workflow
- [CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md) — Contributor Covenant

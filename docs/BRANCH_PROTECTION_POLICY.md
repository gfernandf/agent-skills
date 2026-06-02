# Branch Protection Policy

Status: required governance baseline
Last updated: 2026-05-28

## Scope

This policy defines the minimum merge/push governance expected for the active
default branch used for releases.

In this repository, the default branch is currently `master`.

## Required Repository Settings

Apply these in GitHub branch protection/rulesets for `master` (or the active
default branch if it changes in the future):

1. Require pull request before merging.
2. Require at least 1 approval.
3. Dismiss stale approvals when new commits are pushed.
4. Require conversation resolution before merge.
5. Restrict who can bypass pull request requirements.
6. Require status checks to pass before merging.

## Required Status Checks

At minimum, branch protection must require these checks:

1. `cognitive-quality-gates`
2. `policy-bundle-governance`
3. `runtime_canary`

Canonical source for this list:

1. `docs/required_status_checks.json`

Operational setup guide:

1. `docs/GITHUB_RULESET_RUNBOOK.md`

## Operational Note

Repository settings cannot be fully enforced from code inside the repository. This
policy is enforced operationally in GitHub settings and verified in-repo via
workflow/job consistency checks against the active branch rules/rulesets.

Production requirement:

1. Branch protection/ruleset must be effectively active on the default branch used for releases.
2. If API verification returns `unverified`, manual UI verification via `docs/GITHUB_RULESET_RUNBOOK.md` is mandatory before production promotion.
3. A failed branch-protection verification outcome is always a no-go for production promotion.
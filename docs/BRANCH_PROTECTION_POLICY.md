# Branch Protection Policy

Status: required governance baseline
Last updated: 2026-05-28

## Scope

This policy defines the minimum merge/push governance expected for `main`/`master`.

## Required Repository Settings

Apply these in GitHub branch protection/rulesets for `main` and `master`:

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
workflow/job consistency checks.
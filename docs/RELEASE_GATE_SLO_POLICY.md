# Release Gate SLO Policy

Status: active
Last updated: 2026-05-28

This document defines the versioned policy used by the release readiness gate.

## 1. Policy File

Canonical file:

1. `.github/release_gate_policy.json`

Purpose:

1. Version release-gate decision criteria.
2. Avoid ad-hoc threshold behavior in workflow scripts.

## 2. Profiles

Current profiles:

1. `strict`
2. `transitional`

Usage in CI:

1. push to `main`/`master`: `strict`
2. PR/schedule/manual dispatch: `transitional`

## 3. Controlled Fields

Policy fields per profile:

1. `allow_trend_unverified`
2. `allow_missing_runtime_executive_summary`
3. `max_high_failures`
4. `max_medium_failures`
5. `dx_allowed_slo_statuses`
6. `trend_allowed_slo_statuses`

## 4. Governance Rules

1. Any change to `.github/release_gate_policy.json` requires explicit review.
2. `strict` profile must remain release-safe (no high-severity bypass).
3. Temporary relaxation should happen in `transitional` only and be justified.
4. Exceptions for individual checks must follow `docs/RELEASE_EXCEPTIONS_POLICY.md`.

## 5. Change Procedure

1. Update `.github/release_gate_policy.json`
2. Run workflow validation (`tooling/verify_workflow_embedded_python.py`)
3. Run local gate simulation using desired profile
4. Include rationale in PR/release notes

## 6. Related

1. `tooling/generate_release_readiness_gate.py`
2. `docs/CI_AND_TESTING.md`
3. `docs/PRODUCT_100_EXECUTION_PLAN.md`
4. `docs/RELEASE_EXCEPTIONS_POLICY.md`

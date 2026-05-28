# Release Exceptions Policy

Status: active
Last updated: 2026-05-28

This policy defines how temporary exceptions are allowed in the release readiness
gate without weakening governance discipline.

## 1. Principle

Exceptions are temporary, explicit, and auditable.

No silent bypass is allowed.

## 2. Allowed Scope

An exception may only target a specific release gate `check_id`.

Examples:

1. `trend_slo_status`
2. `trend_report_status`

Exceptions must not be used to permanently skip critical safety controls.

## 3. Required Fields

Exceptions file JSON format:

```json
{
  "exceptions": [
    {
      "check_id": "trend_slo_status",
      "approved_by": "repo-owner",
      "reason": "insufficient historical samples during bootstrap",
      "expires_at": "2026-06-15T00:00:00Z"
    }
  ]
}
```

Required fields per exception:

1. `check_id`
2. `approved_by`
3. `reason`
4. `expires_at` (UTC ISO-8601)

## 4. Behavior

1. Missing/invalid exception entries are reported in gate output.
2. Expired exceptions are ignored and reported.
3. Applied exceptions are listed in `exceptions_applied` within gate report.
4. Exceptions can downgrade a high-severity failure to medium severity for temporary operation.

## 5. Repository Location

Recommended path:

1. `.github/release_exceptions.json`
2. Template: `.github/release_exceptions.example.json`

The file should be created only when needed and removed when no longer required.

## 6. Governance Rules

1. Every exception must have explicit approver identity.
2. Every exception must include a short remediation reason.
3. Every exception must include a near-term expiry date.
4. Exception usage must be referenced in release notes.

## 7. Related

1. `docs/PRODUCTION_READINESS.md`
2. `docs/PRODUCT_100_EXECUTION_PLAN.md`
3. `tooling/generate_release_readiness_gate.py`

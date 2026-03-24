# Capabilities — Backend Status

> **Date**: 2026-03-25 | **Functional**: 122/122 | **Stub-only**: 0

All 122 capabilities have functional runtime bindings. The 37 capabilities
that previously had no binding (identity.\*, integration.\*, task.\*) now use
**in-memory baseline services** — deterministic Python modules that implement
the contract with local data structures instead of calling external systems.

---

## Baseline services (in-memory, no external deps)

| Domain | Service module | Capabilities | Data store |
|---|---|---|---|
| identity.\* | `official_services/identity_baseline.py` | 10 | Dicts: `_ROLES`, `_PRINCIPALS`, `_PERMISSIONS` |
| integration.\* | `official_services/integration_baseline.py` | 12 | Dicts: `_CONNECTORS`, `_RECORDS`, `_EVENTS` |
| task.\* | `official_services/task_baseline.py` | 15 | Dicts: `_CASES`, `_APPROVALS`, `_INCIDENTS`, `_MILESTONES` |

Each baseline module is registered via a service descriptor in `services/official/`
and wired through bindings in `bindings/official/`. All 37 capabilities pass the
batch test suite (`test_capabilities_batch.py`) end-to-end.

---

## Upgrading to real backends

When connecting to production systems, replace the baseline binding for each
capability with a new binding that targets the real service:

| Domain | Target system examples | Integration approach |
|---|---|---|
| identity.\* | Entra ID, Okta, Keycloak | OpenAPI binding to IAM REST API |
| integration.\* | Workato, MuleSoft, custom REST bridge | OpenAPI binding per connector |
| task.\* | Jira, ServiceNow, custom task API | OpenAPI binding to ticketing REST API |

The baseline bindings remain available as fallback or for offline/testing use.
Override precedence: local override → environment-preferred → official default.

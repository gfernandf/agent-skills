# OpenAPI Construction Packages

Date: 2026-03-11
Status: Execution baseline
Scope: Package-based implementation plan for OpenAPI construction before broad capability population

## Objective

Define implementation work in bounded packages by scope, each ending with a commit.
This plan assumes capabilities remain abstract and canonical in the registry.

## Execution Rules

1. Package boundaries are scope-driven, not capability-count driven.
2. Each package ends with one commit that is green for its acceptance checks.
3. Do not change capability definitions in registry during construction packages.
4. Keep pythoncall defaults as fallback until OpenAPI behavior is verified.
5. Verify from local agent-skills instances, never relying on centralized runtime execution.

## Package 1: OpenAPI Runtime Hardening

### Scope

- Strengthen OpenAPI invocation behavior for real services.
- Freeze minimum runtime-level policies for HTTP invocation.

### In Scope

1. Improve HTTP request handling in runtime/openapi_invoker.py.
2. Standardize timeout/error classification behavior at invoker boundary.
3. Add explicit metadata capture needed for tracing and diagnostics.

### Out of Scope

1. Capability-specific mappings.
2. Consumer-facing public API endpoints.

### Deliverables

1. Runtime code updates in OpenAPI invoker path.
2. Tests focused on OpenAPI runtime behaviors.
3. Documentation updates for invocation policy.

### Commit Gate

1. Unit/integration checks for openapi invoker pass.
2. Existing smoke and contracts remain green.

### Suggested Commit

`openapi: harden runtime invoker behavior`

## Package 2: OpenAPI Verification Infrastructure

### Scope

- Consolidate reusable local-instance OpenAPI verification harness.

### In Scope

1. Generic scenario runner in tooling/verify_openapi_bindings.py.
2. Reusable local mocks in tooling/openapi_harness/.
3. Declarative scenario files in tooling/openapi_scenarios/.
4. JSON reporting for CI integration.

### Out of Scope

1. Real external service onboarding beyond selected pilot services.

### Deliverables

1. Harness supports single scenario and all scenarios.
2. Compatibility wrapper retained for existing command usage.
3. At least one validated scenario (already achieved with data.schema.validate).

### Commit Gate

1. `python tooling/verify_openapi_bindings.py --all` passes locally.
2. Existing verification commands still work.

### Suggested Commit

`openapi: add reusable local verification harness`

## Package 3: Security and Error Contract Foundation

### Scope

- Finalize adapter-facing error model and security baseline for OpenAPI paths.

### In Scope

1. Freeze deterministic runtime-to-HTTP error mapping.
2. Define auth and sensitive-field redaction policy for OpenAPI paths.
3. Align observability fields with error handling contract.

### Out of Scope

1. Full consumer-facing API implementation.

### Deliverables

1. Error contract document and implementation notes.
2. Security policy document for OpenAPI usage.
3. Runtime hooks or adapter stubs prepared for enforcement.

### Commit Gate

1. Error contract approved and referenced by implementation docs.
2. No regressions in runtime logs/redaction behavior.

### Suggested Commit

`openapi: freeze error contract and security baseline`

## Package 4: CI Quality Gates for OpenAPI

### Scope

- Promote OpenAPI verification to CI as a first-class gate.

### In Scope

1. Add CI job for OpenAPI scenario verification.
2. Persist scenario report artifacts.
3. Fail pipeline on OpenAPI scenario regressions.

### Out of Scope

1. Full matrix against all future capabilities.

### Deliverables

1. Workflow updates.
2. OpenAPI verification report artifact in CI.

### Commit Gate

1. CI workflow runs OpenAPI verification successfully on baseline scenarios.
2. Existing jobs remain stable.

### Suggested Commit

`ci: add openapi verification gate`

## Package 5: Real-Service Pilot Integration

### Scope

- Replace mock path for pilot capability with a real OpenAPI service path.

### In Scope

1. Introduce real service descriptor for pilot capability.
2. Update binding mapping as needed without changing capability schema.
3. Add scenario profile for real service validation (or environment-gated run).

### Out of Scope

1. Mass migration of all capabilities.

### Deliverables

1. Real-service service descriptor and binding validated.
2. Documented local setup requirements for instance-level execution.

### Commit Gate

1. Pilot real-service scenario passes in configured local environment.
2. Fallback path remains available.

### Suggested Commit

`openapi: integrate first real service pilot`

## Package 6: Documentation Closure for Construction Phase

### Scope

- Close construction stage with operational docs for team execution.

### In Scope

1. How-to: add new OpenAPI binding and service safely.
2. How-to: add new scenario and mock for harness.
3. Construction completion checklist and promotion criteria to population stage.

### Out of Scope

1. Full population runbook for all capabilities.

### Deliverables

1. Updated OpenAPI docs set with clear handoff to population phase.

### Commit Gate

1. Documentation linked from README and OpenAPI phase docs.
2. Team can execute next capability onboarding from docs only.

### Suggested Commit

`docs: close openapi construction phase guidance`

## Completion Criteria for Construction Stage

Construction stage is complete when:

1. Runtime OpenAPI behavior is hardened for real-service use.
2. Reusable verification harness is in place and CI-gated.
3. Error and security contracts are frozen and documented.
4. At least one pilot capability runs through a real OpenAPI service.
5. Documentation is sufficient to start capability population in batches.

## Start Order

1. Package 1
2. Package 2
3. Package 3
4. Package 4
5. Package 5
6. Package 6

This order minimizes rework by stabilizing runtime and verification before scaling service onboarding.

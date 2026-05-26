# RFC-0006: Legacy Retirement Matrix and Cutover Gates

Status: Draft
Date: 2026-05-26
Depends on: RFC-0001 through RFC-0005

## 1. Purpose

Define a bounded migration policy so ORCA reaches a clean final architecture without indefinite dual-path maintenance.

## 2. Migration Policy

1. Legacy support is temporary and explicitly bounded.
2. Canonical behavior is implemented only in the new core.
3. Legacy layers are compatibility projections, not feature surfaces.
4. Each migration stage has measurable cutover gates.

## 3. Retirement Matrix

### 3.1 Execution

1. Legacy component: sync-first execution ownership.
2. Canonical replacement: async-first execution ownership.
3. Temporary bridge: sync adapter over async core.
4. Retirement gate:
   - All core lifecycle operations pass via async core.
   - No runtime feature branch targets legacy execution internals.

### 3.2 Run model

1. Legacy component: minimal run model (running/completed/failed).
2. Canonical replacement: RunStore v2 lifecycle model.
3. Temporary bridge: legacy response projection from RunStore v2.
4. Retirement gate:
   - APIs and SDKs read canonical statuses.
   - Legacy status projection no longer required by supported clients.

### 3.3 Human-in-the-loop

1. Legacy component: exception-only confirmation flow.
2. Canonical replacement: persisted waiting_for_human lifecycle state.
3. Temporary bridge: exception mapping to persisted approval state.
4. Retirement gate:
   - approve/deny lifecycle is used in all HITL scenarios.
   - Exception-only flow removed from runtime control path.

### 3.4 Events

1. Legacy component: log-centric unversioned runtime events.
2. Canonical replacement: versioned EventStore contract.
3. Temporary bridge: log projection from canonical events.
4. Retirement gate:
   - Streaming and trace APIs read from EventStore.
   - Operators use canonical event schema for automation.

### 3.5 Side effects

1. Legacy component: step metadata without durable effect ledger.
2. Canonical replacement: SideEffectLedger with idempotency and replay policy.
3. Temporary bridge: step metadata references to effect records.
4. Retirement gate:
   - External actions are recorded in ledger by default.
   - Replay policy enforcement no longer bypassable.

## 4. Cutover Gates (Global)

Cutover to clean architecture is approved only when all gates pass:

1. Functional gates:
   - resume, replay, fork, approve, deny all pass end-to-end tests.
   - side-effect replay safety tests pass for use_recorded_result and require_human flows.

2. Observability gates:
   - canonical events emitted for full run lifecycle.
   - trace/checkpoint/event APIs return consistent run views.

3. Compatibility gates:
   - supported clients can operate through canonical APIs or projection adapters.
   - migration notices and deprecation warnings are in place.

4. Operational gates:
   - no regressions in baseline reliability suite.
   - incident rollback plan validated for first cutover release.

## 5. Deprecation and Removal Policy

1. Stage A: announce deprecation and publish migration guide.
2. Stage B: keep compatibility layer read-only (no new features).
3. Stage C: remove legacy code paths and documentation references.

## 6. Documentation and Communication Requirements

1. Update docs/ASYNC_EXECUTION.md to canonical durable semantics.
2. Update docs/RUNNER_GUIDE.md and docs/OBSERVABILITY.md to canonical state/event model.
3. Publish migration notes in API changelog and release notes.

## 7. Final State Definition

ORCA final architecture is considered clean when:

1. Runtime has a single canonical execution core.
2. Durable lifecycle is first-class across all surfaces.
3. Side-effect safety is mandatory for external actions.
4. Legacy projections are fully removed.

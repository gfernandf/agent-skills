## Change Type

- [ ] Architecture-affecting change
- [ ] Runtime implementation
- [ ] Registry/governance tooling
- [ ] Documentation only

## Scope Classification (Required for Architecture-affecting Changes)

- [ ] Pattern transfer into ORCA core
- [ ] Optional adapter integration
- [ ] Operational substrate support

Scope statement:

<!-- Explain in 3-6 lines what this PR changes and why. -->

## Target Architecture Alignment

- [ ] I reviewed docs/TARGET_ARCHITECTURE.md
- [ ] This PR preserves OSS-first baseline production path
- [ ] This PR does not require paid SaaS for baseline operation

## Design Invariants Impact Matrix

Mark impact and explain if non-trivial.

- Contract stability: [ ] none [ ] low [ ] medium [ ] high
- Local-first viability: [ ] none [ ] low [ ] medium [ ] high
- Deterministic governance: [ ] none [ ] low [ ] medium [ ] high
- Safety continuity: [ ] none [ ] low [ ] medium [ ] high
- Adapter isolation: [ ] none [ ] low [ ] medium [ ] high
- Observability continuity: [ ] none [ ] low [ ] medium [ ] high

Notes:

<!-- Required when any item is medium/high. -->

## Backward Compatibility

- [ ] Capability contract semantics unchanged
- [ ] Runtime API compatibility preserved or migration path documented
- [ ] Existing CI guardrails remain valid

Compatibility plan:

<!-- Describe compatibility guarantees and any migration/deprecation path. -->

## Rollback Plan

<!-- Describe safe rollback steps if deployment or validation fails. -->

## Validation Evidence

- [ ] Local instance validation executed
- [ ] CI-equivalent checks executed
- [ ] Catalog/governance freshness checks executed when applicable

Commands/evidence:

<!-- Paste commands run and summarize results. -->

## Explicit Non-Goals

<!-- List what this PR intentionally does not do. -->

## Links

- Target architecture: docs/TARGET_ARCHITECTURE.md
- Architecture execution RFC: docs/rfcs/RFC-0007-OSS-FIRST-TARGET-ARCH-EXECUTION.md
- Progress snapshot: docs/TARGET_ARCH_PROGRESS.md

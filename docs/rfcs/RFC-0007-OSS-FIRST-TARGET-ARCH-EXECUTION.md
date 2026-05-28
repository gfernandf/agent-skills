# RFC-0007: OSS-First Target Architecture Execution and Governance

Status: Draft
Date: 2026-05-28
Related: docs/TARGET_ARCHITECTURE.md, docs/PROJECT_STATUS.md, docs/CROSS_REPO_ARCHITECTURE.md, docs/rfcs/RFC-0001-ORCA-RUNTIME-BLUEPRINT.md

## 1. Purpose

Establish a single execution and governance model for delivering the target architecture without drift,
while preserving ORCA as an open-source, production-capable runtime.

This RFC operationalizes three things:

1. How architecture changes must be proposed (RFC + PR contract).
2. How changes are evaluated against non-negotiable invariants.
3. How progress is measured and reported by strategic pillar.

## 2. Problem Statement

Target architecture intent is now explicit in docs/TARGET_ARCHITECTURE.md, but implementation can still drift if:

1. Platform references are interpreted as mandatory vendor integrations.
2. Changes do not declare whether they are pattern transfer vs optional adapter.
3. Progress is reported qualitatively without measurable completion criteria.

## 3. Decision

Adopt an OSS-first architecture change protocol:

1. Every architecture-impacting proposal must classify scope as:
   - pattern transfer,
   - optional adapter, or
   - operational substrate.
2. Every proposal must include explicit impact against design invariants.
3. Every proposal must define backward compatibility and rollback strategy.
4. Strategic progress must be tracked against the Definition of Done in docs/TARGET_ARCHITECTURE.md.

## 4. Mandatory Architecture PR Contract

An architecture PR is acceptable only if it includes all sections below:

1. Scope classification.
2. Invariant impact matrix (contract stability, local-first viability, deterministic governance, safety continuity, adapter isolation, observability continuity).
3. Backward-compatibility plan.
4. Rollback plan.
5. Validation evidence plan (local instance + CI alignment).
6. Explicit non-goals for that change.

Reference template: .github/PULL_REQUEST_TEMPLATE.md

## 5. Progress Accounting Model

Progress is measured per strategic pillar using criteria from docs/TARGET_ARCHITECTURE.md.

Scoring model:

1. Each criterion is scored in [0.0, 1.0].
2. Pillar completion % = average(criteria scores) * 100.
3. Overall completion % = average(all pillar completion %).

Evidence source of truth:

1. docs/PROJECT_STATUS.md
2. Runtime and tooling implementation state in repository
3. CI/workflow guardrail behavior

Current snapshot is maintained in docs/TARGET_ARCH_PROGRESS.md.

## 6. Guardrails

1. No proposal may require paid SaaS for baseline OSS production path.
2. No proposal may change canonical capability semantics without explicit approval.
3. No proposal may introduce unisolated vendor lock-in in runtime core.
4. No proposal may degrade safety or observability guarantees.

## 7. Rollout Plan

1. Stage A: Governance adoption
   - Use PR template for all architecture-affecting changes.
   - Keep RFC-0007 as policy reference in reviews.
2. Stage B: Pillar execution
   - Drive implementation by pillar DoD and progress report.
3. Stage C: Monthly architecture checkpoint
   - Recompute progress % and update docs/TARGET_ARCH_PROGRESS.md.

## 8. Success Criteria

1. Architecture PRs are consistently reviewable with low ambiguity.
2. "Pattern transfer vs integration" is explicit in all strategic work.
3. Progress and gaps are visible as measurable percentages, not narrative only.
4. ORCA remains OSS-first and production-capable without mandatory external platforms.

## 9. Non-Goals

1. Defining implementation details for every pillar in this RFC.
2. Forcing specific vendor products into runtime core.
3. Replacing existing RFC-0001 to RFC-0006 content.

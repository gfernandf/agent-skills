# Target Architecture (Canonical)

Status: Active reference
Last updated: 2026-05-28

This document is the single source of truth for what we are building at a high level.

## North Star

Build a local-first, policy-safe agent runtime where capability contracts remain canonical,
execution is durable, promotion is governed, and external developer experience is productized.

Why this shape matters:

1. It keeps the runtime easy to run locally while still behaving like a production system.
2. It turns governance into an auditable contract, not a loose convention.
3. It lets us improve durability, policy, and DX independently without changing capability IDs.
4. It favors optional adapters over lock-in, so the core stays portable and maintainable.

## Strategic Stance (OSS-first)

ORCA remains open source and production-capable on its own.

Default interpretation of the target stack is:

1. Adopt the best architectural patterns from leading platforms.
2. Keep ORCA core self-sufficient for deployment and DX.
3. Provide integrations as optional adapters, never as mandatory dependencies.

This means we are primarily taking what works (durability semantics, policy model,
developer-product ergonomics), not forcing users to adopt specific vendors.

Strategic target stack:

1. Temporal for durability.
2. dbt/Dagster for contracts, artifacts, and promotion workflows.
3. Kubernetes/OPA for policy enforcement and tenancy.
4. Stripe/Vercel for developer experience and distribution.
5. LangGraph as optional integration target, not runtime foundation.

## Architecture Boundaries

1. `agent-skill-registry` is the source of truth for contracts and catalog artifacts.
2. `agent-skills` is the execution runtime and integration layer.
3. Capability contracts are stable canonical interfaces and are not changed by runtime integration work unless explicitly approved.
4. Real execution validation must run from each local `agent-skills` instance where the package is deployed.
5. ORCA core must not require paid SaaS platforms to run in production.

## Design Invariants (Non-Negotiable)

These invariants must stay true across all migrations.

1. Contract stability: capability IDs and contract semantics remain canonical-first.
2. Local-first viability: full baseline execution path works without hosted control planes.
3. Deterministic governance: promotion and catalog generation remain reproducible and CI-verifiable.
4. Safety continuity: no migration may reduce current trust/gate/confirmation guarantees.
5. Adapter isolation: third-party integrations are optional and isolated behind adapter boundaries.
6. Observability continuity: traceability and auditability must remain end-to-end during transitions.

## Current Alignment Snapshot

### Implemented

1. Local-first runtime execution with deterministic fallbacks and broad capability coverage.
2. Checkpoint/run persistence primitives and resume/replay APIs.
3. Promotion and governance tooling with CI verification and artifact generation.
4. Kubernetes baseline deployment via Helm.
5. LangGraph/LangChain adapter support as integration surface.

### Partial

1. Durability: implemented via internal checkpoint + run-store model, not via Temporal workflows yet.
2. Policy/tenancy: runtime policy and JWT tenant isolation exist, but OPA is not integrated as the policy decision point.
3. Contracts/artifacts/promotion: operationally mature with custom tooling, but not orchestrated by Dagster/dbt.

### Not Started

1. Temporal-native workflow orchestration.
2. Dagster/dbt-based contract and promotion pipelines.
3. Stripe/Vercel developer-experience platform layer.

These are future platform alignments, not blockers for the current architecture.
The present stack already delivers the core advantages we care about: stable
contracts, local-first execution, reproducible governance, and clear promotion
evidence.

## Decision Rules

1. Do not treat LangGraph as mandatory runtime substrate.
2. Prefer composable adapters over framework lock-in.
3. Keep governance and catalog generation CI-enforced.
4. Prioritize migration paths that preserve existing capability IDs and behavior.

## Sequencing (Execution Order)

1. Foundation migration: durability and policy substrate (Temporal + OPA integration plan).
2. Delivery migration: Dagster/dbt orchestration for contracts, artifacts, and promotion.
3. Product layer: Stripe/Vercel DX and external distribution surfaces.

## Platform Value We Intend To Reuse

This section clarifies intent: we are adopting platform patterns and operational qualities,
not blindly importing vendor architecture.

### Adoption Modes

Every platform mention must be classified into one of these modes:

1. Pattern transfer: ORCA implements equivalent behavior in its own core.
2. Optional adapter: ORCA provides interoperability, but users can ignore it.
3. Operational substrate: ORCA supports a deployment/runtime substrate without core lock-in.

Default target by platform:

1. Temporal: pattern transfer first, optional adapter second.
2. Dagster/dbt: operational substrate for delivery pipelines, not runtime core dependency.
3. Kubernetes/OPA: operational substrate for production policy/tenancy.
4. Stripe/Vercel: pattern transfer for DX/distribution.
5. LangGraph: optional adapter.

### Temporal

What we recover as value:

1. Durable workflow execution semantics (history, retries, timers, resume safety).
2. Deterministic orchestration guarantees for long-running skill execution.
3. Failure recovery model with explicit workflow state transitions.

Why this is better than a brittle ad hoc runner:

1. Retries and recovery become deliberate, not accidental.
2. Long-running work can be resumed without losing provenance.
3. The execution model stays inspectable enough to support governance.

What we are not doing:

1. Replacing ORCA contracts/skills model with vendor-specific workflow definitions.
2. Coupling capability identity or registry governance to Temporal primitives.

### Dagster / dbt

What we recover as value:

1. Orchestrated delivery pipelines for contract validation, catalog regeneration, and promotion.
2. Asset lineage and materialization mindset for reproducible artifacts.
3. Declarative data/contract checks as enforceable gates.

Why this matters for ORCA today:

1. It makes release evidence materialize from the same source that defines the
	contracts.
2. It reduces duplication between CI checks, reports, and promotion inputs.
3. It gives maintainers a clean line between source, artifact, and decision.

What we are not doing:

1. Moving runtime skill execution into data-pipeline engines.
2. Making dbt a runtime dependency for local execution of capabilities.

### Kubernetes / OPA

What we recover as value:

1. Multi-tenant operational control plane for deployment and isolation.
2. Externalized policy decision model (OPA) for auditable authorization/safety constraints.
3. Standardized runtime packaging and environment promotion through Kubernetes primitives.

What we are not doing:

1. Replacing all in-runtime policy checks immediately; migration is staged.
2. Forcing centralized hosted execution when local-instance validation is required.

### Stripe-like DX / Vercel-like distribution

What we recover as value:

1. Stripe-like DX means fast onboarding, predictable API ergonomics, excellent docs,
	and copy/paste quickstarts with trustworthy examples.
2. Vercel-like experience means low-friction deployment and preview/promote flows
	with clear environment boundaries.
3. Developer productization: clear lifecycle from local run to production-ready integration.

What we are not doing:

1. Stripe-like DX does not imply we must integrate Stripe billing APIs in the core runtime.
2. Vercel-like deployment UX does not imply ORCA must run only on Vercel.
3. ORCA OSS production path must remain complete without Stripe/Vercel accounts.

### LangGraph

What we recover as value:

1. Ecosystem interoperability surface for teams already using LangChain/LangGraph.
2. Optional adapter-level compatibility for tool invocation.

What we are not doing:

1. Making LangGraph the mandatory execution substrate for ORCA runtime.

## Proposed Implementation Architecture

### Layer A: Canonical Contract Plane (source of truth)

1. Repository: `agent-skill-registry`.
2. Responsibilities: capability/skill contracts, vocabulary, governance, catalog artifacts.
3. Rule: contracts remain stable and canonical; runtime migrations cannot mutate semantics by default.

### Layer B: Runtime Execution Plane (local-first)

1. Repository: `agent-skills`.
2. Responsibilities: workflow execution, bindings, checkpointing, traceability, customer-facing adapters.
3. Near-term evolution: migrate durability internals toward Temporal-backed orchestration without breaking skill contracts.

### Layer C: Delivery and Promotion Plane

1. Purpose: deterministic validation, artifact generation, and registry promotion workflows.
2. Near-term evolution: introduce Dagster/dbt as orchestrators around existing governance checks and catalog generation.
3. Rule: preserve CI-equivalent validation sequence and catalog freshness guarantees.

### Layer D: Policy and Tenancy Plane

1. Purpose: centralized policy evaluation and multi-tenant controls.
2. Near-term evolution: integrate OPA decision points while preserving existing runtime safety gates during transition.
3. Deployment context: Kubernetes as default production control surface, Helm baseline first.

### Layer E: Developer Experience Plane

1. Purpose: Stripe-like API/docs/onboarding quality and Vercel-like deployment ergonomics.
2. Components: fast starters, API parity examples, environment promotion UX, high-signal diagnostics.
3. Non-goal: billing/provider coupling in runtime core.

## Definition of Done by Strategic Pillar

### Durability (Temporal-inspired)

Done when:

1. Long-running skills survive process restart without semantic drift.
2. Retry/timer/resume behavior is explicit and test-covered.
3. Existing checkpoint/replay APIs preserve backward compatibility.

### Contracts, Artifacts, Promotion (Dagster/dbt-inspired)

Done when:

1. Registry validation and catalog generation run as orchestrated, reproducible pipeline stages.
2. Promotion flow emits traceable lineage from source change to generated artifacts.
3. CI and local execution produce equivalent pass/fail outcomes for governance gates.

### Policy and Tenancy (Kubernetes/OPA-inspired)

Done when:

1. Policy decisions are externally explainable and auditable.
2. Tenant isolation guarantees are enforced consistently across runtime surfaces.
3. Existing in-runtime safety controls remain active during migration.

### Developer Experience and Distribution (Stripe-like/Vercel-like)

Done when:

1. Time to first successful execution from clean setup is explicitly measured and improved.
2. API docs, quickstarts, and examples are parity-validated against real runtime behavior.
3. Environment promotion flow (dev/preview/prod) is documented and reproducible.
4. None of the above requires paid SaaS accounts for baseline OSS production path.

## Non-Goals (Explicit)

1. Rewriting ORCA runtime around any single external framework.
2. Replacing canonical contract governance with vendor-native contract stores.
3. Requiring Stripe, Vercel, Temporal Cloud, or managed services for baseline production readiness.
4. Treating LangGraph compatibility as a prerequisite for ORCA execution.

## Scope Guardrails (To Prevent Drift)

1. If a proposal changes capability contract semantics, it must be explicit and separately approved.
2. If a proposal introduces vendor lock-in at runtime core, reject or isolate behind adapter boundaries.
3. If a proposal claims "Stripe-like DX", it must specify concrete UX metrics (time-to-first-success, docs parity, integration steps).
4. If a proposal claims "Vercel-like", it must define deployment promotion flow and preview behavior, not only hosting target.
5. Any new integration with third-party platforms must satisfy "optional adapter" policy:
	ORCA runtime + governance + local deployment flow continue to function without it.

## Architecture Change Checklist (Anti-Surprise)

Any architecture PR/RFC should include, at minimum:

1. Scope classification: pattern transfer, optional adapter, or operational substrate.
2. Impact statement on invariants (contract stability, local-first viability, safety, observability).
3. Backward-compatibility plan for capability contracts and runtime APIs.
4. Rollback strategy if migration stage fails.
5. Validation evidence plan: local instance checks plus CI gate alignment.
6. Explicit statement of what is out of scope for that change.

## Decision Test (Quick Check)

For every roadmap item, ask:

1. Does this improve ORCA's own production readiness and DX even if no external platform is used?
2. Is this a pattern transfer into ORCA core, or a user-facing optional integration?
3. If integration exists, can users ignore it and still get full baseline value from ORCA?

If answer to (1) is no, item is out of scope for core architecture.

## Pointers

1. ORCA foundation: `ORCA.md`
2. Cross-repo responsibilities: `docs/CROSS_REPO_ARCHITECTURE.md`
3. Runtime status snapshot: `docs/PROJECT_STATUS.md`
4. OpenAPI construction baseline: `docs/OPENAPI_CONSTRUCTION_PACKAGES.md`
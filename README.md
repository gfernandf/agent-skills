# Agent Skill Registry

An open registry of reusable **AI agent skills** and **capability definitions**.

The registry provides a standardized, declarative way to define:

- primitive **capabilities**
- composable **skills (workflows)**
- shared **vocabulary**
- machine-readable **catalogs**

It acts as the **source of truth for agent workflows** that can be executed by compatible runtimes.

## Runtime Quality & Observability

- Observability implementation details: `docs/OBSERVABILITY.md`
- Pre-MCP/OpenAPI readiness and consistency snapshot: `docs/PRE_MCP_OPENAPI_READINESS.md`

## Documentation Index

- Current project closure snapshot: `docs/PROJECT_STATUS.md`
- 10-minute onboarding for new contributors: `docs/ONBOARDING_10_MIN.md`
- Runtime runner architecture and operations: `docs/RUNNER_GUIDE.md`
- Observability and trace/redaction controls: `docs/OBSERVABILITY.md`
- Pre-MCP/OpenAPI readiness baseline: `docs/PRE_MCP_OPENAPI_READINESS.md`
- OpenAPI v1 phase-0 governance and technical foundation: `docs/OPENAPI_PHASE0_FOUNDATION.md`
- OpenAPI v1 phase-1 smoke rollout plan: `docs/OPENAPI_PHASE1_SMOKE_PLAN.md`
- OpenAPI construction packages and commit strategy: `docs/OPENAPI_CONSTRUCTION_PACKAGES.md`
- OpenAPI error and security baseline: `docs/OPENAPI_ERROR_SECURITY_BASELINE.md`

---

# Why this exists

AI agents increasingly rely on structured tools and workflows.

However, most implementations today are:

- tightly coupled to a specific framework
- implemented imperatively in code
- difficult to reuse across systems
- inconsistent in naming and structure

The **Agent Skill Registry** addresses this by providing:

- a **common vocabulary**
- a **declarative workflow model**
- a **shared registry of reusable skills**
- a **machine-readable catalog for runtimes**

The goal is to make agent capabilities **discoverable, composable, and reusable**.

---

# Core Concepts

The registry defines two fundamental building blocks.

## Capabilities

Capabilities represent **primitive operations**.

They define a **contract** describing what an operation does, including:

- inputs
- outputs
- execution properties
- optional metadata

Examples:

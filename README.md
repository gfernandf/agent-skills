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

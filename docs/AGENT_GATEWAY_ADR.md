# ADR-001: Agent-Facing Skill Gateway Layer

## Status

Accepted

## Date

2025-01

---

## Context

The agent-skills runtime already provides a `NeutralRuntimeAPI`, an HTTP
OpenAPI server, and an MCP stdio bridge. These are protocol-correct but not
agent-semantic: they expose what the runtime can do, not what an agent
orchestrating a workflow needs to ask.

An agent coordinating workflows needs four first-class operations:

1. **discover** — "Which skill solves this job-to-be-done?"
2. **run** — "Execute this skill with these inputs."
3. **attach** — "Apply this skill to an existing execution target (a run, an
   output, a transcript, an artifact)."
4. **list** — "Show me all skills available for this domain or role."

None of these exist as first-class operations today. `discover` and `attach`
do not exist at all. `run` and `list` require knowing internal identifiers and
the governance structure of the registry.

Additionally, skills carry no canonical metadata about **how they should be
invoked** (direct call vs. attach), **what they produce** (enrichment,
read-only result, control signal), or **what targets they operate on**. This
information is implicit in the skill name and description.

---

## Decision

### 1. Add Canonical Classification Fields to Registry Skills

Introduce a `classification` block under `metadata` in every skill YAML. The
schema is defined in `agent-skill-registry/docs/SKILL_FORMAT.md`.

| Field | Values | Meaning |
|---|---|---|
| `role` | `procedure \| utility \| sidecar` | How the skill participates in a workflow |
| `invocation` | `direct \| attach \| both` | How the skill is triggered |
| `attach_targets` | list: `task \| run \| output \| transcript \| artifact` | Required when `invocation ∈ {attach, both}` |
| `effect_mode` | `read_only \| enrich \| control_signal` | What the skill produces as its primary effect |

Classification is **canonical registry data**, not a gateway overlay. It is
part of the skill contract and travels with the skill across runtimes,
registries, and adapters.

#### Role semantics

| Role | Definition | Discovery behavior |
|---|---|---|
| `procedure` | Solves a business objective end-to-end | Recommended as primary match in `discover` |
| `utility` | Technical building block, composable | Recommended as secondary match or when explicitly requested |
| `sidecar` | Auxiliary skill that needs a live execution target to observe, audit, or control | Excluded from direct-call recommendations; surfaced only via `attach` |

#### Invocation and attach_targets rules

- `role=sidecar` → `invocation` must not be `direct`
- `invocation ∈ {attach, both}` → `attach_targets` must list at least one valid target type
- `invocation=direct` → `attach_targets` must be absent

### 2. Introduce a Skill Gateway Module

Add a `gateway/` package to agent-skills with the following structure:

| Module | Path | Responsibility |
|---|---|---|
| `SkillGateway` | `gateway/core.py` | Orchestrates all four operations; owns the operation contracts |
| `DiscoveryService` | `gateway/discovery.py` | Implements ranking, filtering, and match scoring |
| `AttachService` | `gateway/attach.py` | Validates attach eligibility and executes against typed targets |
| `GatewayModels` | `gateway/models.py` | `DiscoverResult`, `AttachResult`, `SkillSummary`, `GatewayRequest` |

The gateway wraps the existing `NeutralRuntimeAPI`. It adds agent-semantic
vocabulary on top without modifying runtime execution semantics.

### 3. Extend the CLI with Agent-Facing Commands

Add to `cli/main.py`:

| Command | Description |
|---|---|
| `skills discover <intent>` | Discover and rank skills matching an intent string |
| `skills list [--domain D] [--role R] [--status S]` | List skills with optional filters |
| `skills attach <id> --target-type TYPE --target-ref REF` | Execute a skill against a live target |
| `skills serve [--port N]` | Start the HTTP gateway server |
| `skills mcp` | Start the MCP stdio gateway bridge |

Existing commands (`run`, `describe`, `trace`, `activate`, `skill-governance`,
`doctor`, `explain-capability`, `openapi`, `audit-purge`, `scaffold`,
`package-*`) are not changed.

---

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                Agent / Orchestrator                      │
└──────────────────────┬───────────────────────────────────┘
                       │  discover · run · attach · list
┌──────────────────────▼───────────────────────────────────┐
│            Skill Gateway  (Application Core)             │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────┐  │
│  │  Discovery   │  │  Execution   │  │    Attach      │  │
│  │  Service     │  │  Service     │  │    Service     │  │
│  └──────┬───────┘  └──────┬───────┘  └───────┬────────┘  │
└─────────┼─────────────────┼──────────────────┼───────────┘
          │                 │                  │
┌─────────▼─────────────────▼──────────────────▼───────────┐
│          NeutralRuntimeAPI  (existing facade)             │
│  SkillLoader · CapabilityExecutor · Engine                │
└──────────────────────────────────────────────────────────┘
          │
┌─────────▼──────────────────────────────────────────────┐
│  Adapters  (new CLI subcommands · HTTP serve · MCP mcp) │
└────────────────────────────────────────────────────────┘
```

All adapters consume the `SkillGateway` interface, not `NeutralRuntimeAPI`
directly.

---

## Operation Contracts

### discover

```
Input:
  intent:      str                              # required
  domain:      str | list[str]                  # optional
  role_filter: procedure | utility | sidecar    # optional

Output:
  list[DiscoverResult]                          # sorted descending by score

  DiscoverResult:
    skill_id:    str
    name:        str
    score:       float
    role:        str
    effect_mode: str
    reason:      str
```

**Ranking rules** (applied in order, highest priority first):

1. `role=procedure` > `utility` unless `role_filter=utility` is explicit
2. `status=stable` > `experimental` > others
3. Exact tag match > partial name/description match > no match
4. `effect_mode=read_only` preferred for read-only intent patterns

### run

```
Input:
  skill_id: str
  inputs:   dict
  options:  ExecutionOptions    # optional

Output:
  ExecutionResult               # pass-through from NeutralRuntimeAPI.execute_skill
```

Thin wrapper — adds gateway trace context, delegates entirely to
`NeutralRuntimeAPI.execute_skill`.

### attach

```
Input:
  skill_id:    str
  target_type: task | run | output | transcript | artifact
  target_ref:  str
  inputs:      dict

Output:
  AttachResult:
    skill_id:    str
    target_type: str
    target_ref:  str
    execution:   ExecutionResult
    attached_at: str    # ISO-8601 timestamp
```

**Validation before execution:**

1. Skill must exist and be loadable.
2. Skill's `invocation` must be `attach` or `both`.
3. `target_type` must appear in skill's `attach_targets`.
4. Violation of (2) or (3) → raise `AttachValidationError` with structured reason.

### list

```
Input:
  domain: str    # optional
  role:   str    # optional
  status: str    # optional

Output:
  list[SkillSummary]

  SkillSummary:
    skill_id:    str
    name:        str
    role:        str
    invocation:  str
    effect_mode: str
    status:      str
```

---

## Consequences

### Positive

- Agents get vocabulary-level operations (`discover`, `attach`) alongside
  transport-level execution (`run`).
- Classification is canonical in the registry — portable across all runtimes
  that load skill YAMLs.
- All existing infrastructure (`NeutralRuntimeAPI`, HTTP server, MCP bridge)
  is reused without modification.
- Execution semantics are unchanged; only the routing and recommendation layers
  are new.

### Neutral

- Classification fields are additive to skill YAML — fully backward compatible.
  `metadata._normalize_metadata()` in `runtime/skill_loader.py` passes through
  any unknown dict keys without error.
- Existing CLI commands and HTTP/MCP routes are not renamed or removed.

### Negative

- Discovery ranking is heuristic (tag/name/description matching) until an
  embedding-based index is available for semantic search.
- Attach target validation relies on accuracy of `attach_targets` declared in
  YAML; there is no runtime verification that the target_ref actually exists.

### Operational Guidance (Product Agents)

- Gateway autonomy is intentionally **policy-guided**, not unconstrained.
- Agents should use ranking outputs from `discover` as candidate hints, then
  apply explicit product policy for final skill selection.
- For requests that include observability/control requirements, agents should
  treat sidecar skills as an additional attached workstream, not as a special
  hard-coded exception.
- Product behavior should remain skill-agnostic: any skill classified as
  `role=sidecar` and `invocation=attach|both` is eligible by policy.

### Clarification: Guided vs Free Autonomy

- Guided autonomy: agent decomposes work using gateway primitives (`discover`,
  `execute`, `attach`) under explicit policy constraints and contract checks.
- Free autonomy: agent makes unbounded decisions without deterministic policy.

This ADR standardizes guided autonomy for production reliability and auditability.

---

## Alternatives Considered

### A. Compute classification at the gateway, not in the registry

**Rejected.** Classification is intrinsic to the skill — it belongs in the
registry alongside `inputs`, `outputs`, and `steps`. Computing it at the
gateway creates a second source of truth that diverges whenever a skill is
loaded by a different runtime or registry tooling.

### B. Extend NeutralRuntimeAPI directly with discover/attach

**Rejected.** `NeutralRuntimeAPI` is a protocol-neutral facade, not an
agent-semantic layer. Adding ranking and attach validation to it breaks its
single responsibility.

### C. Add MCP discovery tools directly inside MCPToolBridge

**Rejected.** `MCPToolBridge` is an adapter. Business rules for discovery
ranking and attach validation must not live in an adapter — they need to be
testable and reusable independent of the transport wire format.

---

## References

- `agent-skill-registry/docs/SKILL_FORMAT.md` — classification schema
- `agent-skill-registry/docs/SKILL_ADMISSION_POLICY.md` — admission checklist
- `agent-skills/customer_facing/neutral_api.py` — NeutralRuntimeAPI
- `agent-skills/customer_facing/mcp_tool_bridge.py` — MCPToolBridge
- `agent-skills/customer_facing/http_openapi_server.py` — HTTP OpenAPI server
- `agent-skills/runtime/engine_factory.py` — build_runtime_components()

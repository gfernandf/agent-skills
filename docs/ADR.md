# ADR-001: DAG-Based Step Scheduler

## Status
Accepted

## Context
Skills in agent-skills can have multiple steps with dependencies between them.
We needed a scheduling strategy that:
- Supports parallel execution of independent steps
- Preserves backward-compatible sequential ordering for legacy skills
- Detects circular dependencies at plan time
- Provides fail-fast and graceful degradation modes

## Decision
We chose a **DAG-based scheduler using Kahn's algorithm** for topological ordering with a ThreadPoolExecutor for parallel dispatch.

Key design choices:
1. **Implicit sequential dependencies**: Steps without explicit `depends_on` implicitly depend on the immediately preceding step, preserving v1 sequential semantics.
2. **Sharded state locks**: Namespace-level locks (vars/outputs/working/events) reduce contention vs. a single global lock.
3. **Pool saturation tracking**: Metrics counter when ready steps exceed available workers.

## Alternatives Considered
- **asyncio event loop**: Rejected — ThreadPoolExecutor is simpler and works well with blocking binding calls (HTTP, subprocess MCP).
- **Celery/distributed queue**: Rejected — adds infrastructure dependency for minimal benefit at single-instance scale.
- **Simple sequential loop**: Too limiting — skills with independent steps (e.g., parallel data enrichment) benefit significantly from parallelism.

## Consequences
- (+) Independent steps execute concurrently, reducing wall-clock time
- (+) Backward-compatible with all existing sequential skills
- (-) Thread overhead for small skills (mitigated by configurable `max_workers`)
- (-) `_StateLock` contention at high parallelism (mitigated by sharding in v2)

---

# ADR-002: Safety Gate Architecture

## Status
Accepted

## Context
Agent skills can perform side-effecting operations (write files, send emails, call APIs). We needed a safety model that:
- Prevents unauthorized capability execution
- Supports human-in-the-loop confirmation
- Allows declarative safety policies per capability

## Decision
Safety enforcement uses a **3-layer model**:
1. **Trust levels**: Capability declares minimum trust (sandbox < standard < elevated < privileged); context must meet or exceed.
2. **Confirmation gates**: Capability can require explicit human confirmation (`requires_confirmation: true`).
3. **Mandatory gates**: Pre/post gate capabilities that validate inputs/outputs with configurable failure policies (block/warn/degrade/require_human).

Extracted into a pluggable `PolicyEngine` (ADR-002b) for extensibility.

## Consequences
- (+) Safety chains cannot be bypassed — embedded in execution pipeline
- (+) Declarative per-capability — no central policy file to maintain
- (-) Gate execution adds latency (mitigated by gate capability caching)

---

# ADR-003: CognitiveState v1 Design

## Status
Accepted

## Context
Multi-step skills need structured working memory for reasoning patterns (evaluation, risk analysis, decision justification). Ad-hoc `vars.*` usage leads to naming collisions and opaque state.

## Decision
Introduced **CognitiveState v1** with typed slots:
- `FrameState` (frozen): immutable goal/constraints/success_criteria
- `WorkingState` (mutable): typed cognitive categories (entities, options, criteria, evidence, risks, hypotheses, uncertainties, decisions, messages)
- `OutputState`: structured result metadata
- `TraceState`: execution trace with data lineage

Auto-wiring: `cognitive_hints.produces` in capability specs maps outputs to CognitiveState slots automatically when no explicit `output_mapping` exists.

## Consequences
- (+) Skills can compose rich reasoning patterns without custom state management
- (+) Type-safe slot operations enable validation and tracing
- (-) Learning curve for new developers (mitigated by tutorials)
- (-) Memory footprint per run (acceptable — dies with the run)

---

# ADR-004: Storage Abstraction

## Status
Accepted

## Context
Runtime components (audit, diagnostics, run_store) assume local filesystem via `pathlib.Path`. This prevents cloud-native deployment without code changes.

## Decision
Introduced `StorageBackend` protocol with `LocalFileStorage` default. Components accept an optional `storage_manager` parameter. Path-traversal protection built into the default implementation.

## Consequences
- (+) Cloud backends (S3, GCS, Redis) can be plugged without modifying core runtime
- (+) Default behavior unchanged — zero config for local development
- (-) Migration effort for existing code to adopt the abstraction incrementally

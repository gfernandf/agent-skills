# CognitiveState v1

Date: 2026-03-19

This document describes the CognitiveState v1 extension to the runtime execution model.

CognitiveState v1 adds structured cognitive blocks to `ExecutionState` without
breaking any existing behavior. All legacy fields (`vars`, `outputs`, `events`,
`step_results`, `status`, `trace_id`) remain unchanged and fully functional.

---

## Motivation

The original `ExecutionState` supports flat key-value `vars` and `outputs` that
work well for simple linear skills. Multi-step reasoning skills need:

- an immutable reasoning context (why does this run exist?)
- structured working memory for intermediate cognitive artifacts
- typed result metadata beyond a flat output dict
- data lineage and execution trace for observability
- merge strategies when multiple steps write to the same cognitive slot

CognitiveState v1 addresses all five without duplicating or replacing legacy fields.

---

## Architecture

ExecutionState now contains four cognitive blocks plus an extension point:

```
ExecutionState
├── inputs          (dict)         ── caller-provided, read-only
├── vars            (dict)         ── legacy intermediate values
├── outputs         (dict)         ── legacy final outputs
├── events          (list)         ── runtime event log
├── step_results    (dict)         ── per-step execution records
│
├── frame           (FrameState)   ── immutable reasoning context
├── working         (WorkingState) ── mutable cognitive working memory
├── output          (OutputState)  ── structured result metadata
├── trace           (TraceState)   ── execution trace + metrics
└── extensions      (dict)         ── open namespace for plugins
```

Each block serves a distinct audience:

| Block | Audience | Mutability | Purpose |
|-------|----------|------------|---------|
| frame | steps (read) | frozen | Why does this run exist? Boundaries. |
| working | steps (read/write) | mutable | Intermediate cognitive processing. |
| output | steps (write), caller (read) | mutable | Semantic result metadata. |
| trace | engine (write), ops (read) | mutable | Observability, data lineage. |
| extensions | plugins (read/write) | mutable | Open namespace for future features. |

---

## Data Structures

### FrameState (frozen)

Immutable context established when the run is created. Read-only during execution.

```python
@dataclass(frozen=True)
class FrameState:
    goal: str | None = None
    context: dict[str, Any] = field(default_factory=dict)
    constraints: dict[str, Any] = field(default_factory=dict)
    success_criteria: dict[str, Any] = field(default_factory=dict)
    assumptions: tuple[str, ...] = ()
    priority: str | None = None
```

Usage in step input mappings:

```yaml
input:
  objective: frame.goal
  max_budget: frame.constraints.budget
```

### WorkingState (mutable)

Working memory for multi-step cognitive processing. Dies with the run — NOT
persistent memory. Contains 10 typed cognitive slots:

```python
@dataclass
class WorkingState:
    artifacts: dict[str, Any]                    # named intermediate products
    entities: list[dict[str, Any]]               # identified entities
    options: list[dict[str, Any]]                # candidate options
    criteria: list[dict[str, Any]]               # evaluation criteria
    evidence: list[dict[str, Any]]               # collected evidence
    risks: list[dict[str, Any]]                  # identified risks
    hypotheses: list[dict[str, Any]]             # active hypotheses
    uncertainties: list[dict[str, Any]]          # known unknowns
    intermediate_decisions: list[dict[str, Any]] # reasoning checkpoints
    messages: list[dict[str, Any]]               # conversation accumulator
```

Usage in step input/output mappings:

```yaml
# Write to working memory
output:
  entities: working.entities
  draft: working.artifacts.first_draft

# Read from working memory
input:
  prior_risks: working.risks
  draft_text: working.artifacts.first_draft
```

### OutputState (mutable)

Structured result metadata. Distinct from `outputs` (the legacy flat dict).

```python
@dataclass
class OutputState:
    result: Any = None
    result_type: str | None = None
    summary: str | None = None
    status_reason: str | None = None
```

Usage in step output mappings:

```yaml
output:
  final_summary: output.summary
  quality_label: output.result_type
```

### TraceStep (frozen)

One step's trace entry with data lineage. Generated automatically by the engine.

```python
@dataclass(frozen=True)
class TraceStep:
    step_id: str
    capability_id: str
    status: str
    started_at: datetime | None = None
    ended_at: datetime | None = None
    reads: tuple[str, ...]  = ()     # references read during input mapping
    writes: tuple[str, ...] = ()     # targets written during output mapping
    latency_ms: int | None = None
```

### TraceMetrics

Live aggregate execution metrics updated as steps execute.

```python
@dataclass
class TraceMetrics:
    step_count: int = 0
    llm_calls: int = 0
    tool_calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    elapsed_ms: int = 0
```

### TraceState

Container for execution trace, combining per-step entries with aggregated metrics.

```python
@dataclass
class TraceState:
    steps: list[TraceStep] = field(default_factory=list)
    metrics: TraceMetrics = field(default_factory=TraceMetrics)
```

---

## Namespaces

### Reference Resolution (reading)

The `ReferenceResolver` supports 7 namespaces with access control:

| Namespace | Source | On missing | Path traversal |
|-----------|--------|------------|----------------|
| `inputs` | state.inputs[key] | None | dict only |
| `vars` | state.vars[key] | error | dict only |
| `outputs` | state.outputs[key] | error | dict only |
| `frame` | state.frame.attr | None | dataclass → dict → list |
| `working` | state.working.attr | error | dataclass → dict → list |
| `output` | state.output.attr | None | dataclass → dict → list |
| `extensions` | state.extensions[key] | None | dict → list |

Path traversal resolves nested values by walking through dataclass attributes,
dict keys, and list/tuple indices:

```yaml
# Dataclass attribute access
frame.goal                    → state.frame.goal

# Nested dict key access
frame.constraints.budget      → state.frame.constraints["budget"]

# List index access
working.entities.0            → state.working.entities[0]

# Deep nested path
working.entities.0.name       → state.working.entities[0]["name"]
```

Anything not matching a known namespace is treated as a literal string value.

### Output Mapping (writing)

The `OutputMapper` supports 5 writable namespaces:

| Namespace | Target | Notes |
|-----------|--------|-------|
| `vars` | state.vars | legacy flat dict |
| `outputs` | state.outputs | legacy flat dict |
| `working` | state.working | auto-creates intermediate dicts |
| `output` | state.output | auto-creates intermediate dicts |
| `extensions` | state.extensions | auto-creates intermediate dicts |

Three namespaces are read-only and reject writes:

| Namespace | Reason |
|-----------|--------|
| `inputs` | Caller-provided, immutable |
| `frame` | Frozen dataclass, immutable |
| `trace` | Engine-managed, not step-writable |

---

## Merge Strategies

When multiple steps write to the same target, the merge strategy (declared in
`step.config.merge_strategy`) controls collision behavior:

| Strategy | Behavior |
|----------|----------|
| `overwrite` | Default. Raises error on duplicate target within same step mapping. |
| `append` | For list targets, extends via list concatenation. |
| `deep_merge` | For dict targets, recursively merges keys (overlay wins for non-dict values). |
| `replace` | Unconditionally overwrites, no duplicate error. |

Example in a skill step:

```yaml
- id: collect_risks
  uses: analysis.risk.extract
  config:
    merge_strategy: append
  input:
    text: vars.document_text
  output:
    risks: working.risks
```

---

## Execution Metadata

CognitiveState v1 adds metadata fields to `ExecutionState`:

| Field | Type | Purpose |
|-------|------|---------|
| `state_version` | str | Always `"1.0.0"` for CognitiveState v1 |
| `skill_version` | str \| None | Skill version from spec metadata |
| `iteration` | int | Run iteration counter (for future retry/loop support) |
| `current_step` | str \| None | ID of the step currently executing |
| `parent_run_id` | str \| None | Parent run ID for nested skill composition |
| `updated_at` | datetime \| None | Timestamp of last state mutation |

---

## Trace Enrichment

The `ExecutionEngine` automatically enriches trace data during execution:

1. **Per-step TraceStep**: generated for every step (success or failure), recording:
   - step_id, capability_id, status
   - started_at, ended_at timestamps
   - reads: references resolved during input mapping
   - writes: targets written during output mapping
   - latency_ms: step wall-clock time

2. **Live TraceMetrics**: updated after each step completes:
   - step_count incremented
   - elapsed_ms accumulated
   - llm_calls, tokens_in, tokens_out extracted from step meta when available

3. **StepResult enrichment**: each `StepResult` also carries `reads`, `writes`,
   and `latency_ms` for per-step inspection.

### Data Lineage

The trace records which references each step reads and which targets it writes.
This enables:

- dependency analysis between steps
- impact analysis when a step fails
- audit of which data flows through which capabilities

Example trace output:

```python
state.trace.steps[0].reads   # ("inputs.text", "frame.goal")
state.trace.steps[0].writes  # ("vars.summary", "working.artifacts.draft")
```

---

## Backward Compatibility

CognitiveState v1 is fully backward-compatible:

- All new fields have defaults. Existing code that creates `ExecutionState`
  without the new fields continues to work.
- Legacy `vars`/`outputs`/`events` remain the primary dataflow namespaces.
- The `inputs` → `vars` → `outputs` pipeline is unchanged.
- Reference syntax `inputs.*`, `vars.*`, `outputs.*` works exactly as before.
- Skills that do not use cognitive namespaces are unaffected.

### Migration Path

Skills can adopt CognitiveState v1 incrementally:

1. **No changes needed**: existing skills continue working.
2. **Add frame**: pass `FrameState` at run creation for reasoning context.
3. **Use working memory**: write to `working.*` targets for intermediate cognitive state.
4. **Use output metadata**: write to `output.*` for structured result description.
5. **Leverage trace**: inspect `state.trace` for execution analysis after completion.

---

## Test Coverage

CognitiveState v1 is validated by two dedicated test suites:

- `runtime/test_cognitive_state_regression.py`: 86 tests locking legacy pipeline behavior.
- `runtime/test_cognitive_state_v1.py`: 99 tests validating all new functionality.

Run both via:

```powershell
python -m runtime.test_cognitive_state_regression
python -m runtime.test_cognitive_state_v1
```

---

## Module Changes Summary

| Module | Change |
|--------|--------|
| `runtime/models.py` | Added FrameState, WorkingState, OutputState, TraceStep, TraceMetrics, TraceState. Extended ExecutionState and StepResult. |
| `runtime/execution_state.py` | `create_execution_state` accepts optional frame, skill_version, parent_run_id. |
| `runtime/reference_resolver.py` | Rewritten with path traversal, 7 namespaces, ACL (permissive vs strict). |
| `runtime/output_mapper.py` | Rewritten with 5 writable namespaces, 4 merge strategies, nested writing. |
| `runtime/execution_planner.py` | Validation extended for new writable/read-only namespaces. |
| `runtime/execution_engine.py` | TraceStep generation, TraceMetrics live update, reads/writes tracking. |

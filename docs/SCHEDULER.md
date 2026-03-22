# DAG Scheduler

This document describes the step scheduler used by the execution engine.

## Overview

The scheduler (`runtime/scheduler.py`) replaces the original sequential step loop
with a DAG-based execution model. Steps may run in parallel when their dependencies
allow it.

The scheduler is **backward-compatible**: existing skills that do not declare
`depends_on` continue to execute sequentially with identical semantics.

## Dependency Rules

1. If a step declares `config.depends_on: [step_a, step_b]`, those are its
   explicit dependencies. The step runs only after all listed steps complete.
2. If a step declares `config.depends_on: []` (explicit empty list), it has
   no dependencies and may run in parallel with other independent steps.
3. If a step does NOT declare `depends_on` at all, it implicitly depends on
   the immediately preceding step in declared order. This preserves sequential
   semantics for all existing skills without any changes.

### Examples

Sequential (default — no `depends_on` declared):

```yaml
steps:
  - id: step_a
    uses: capability.one
  - id: step_b
    uses: capability.two    # implicitly depends on step_a
  - id: step_c
    uses: capability.three  # implicitly depends on step_b
```

Execution order: `step_a → step_b → step_c`

Parallel (explicit empty deps):

```yaml
steps:
  - id: fetch_a
    uses: web.page.fetch
    config:
      depends_on: []        # no dependencies
  - id: fetch_b
    uses: web.page.fetch
    config:
      depends_on: []        # no dependencies
  - id: combine
    uses: text.content.template
    config:
      depends_on: [fetch_a, fetch_b]  # waits for both
```

Execution order: `fetch_a ∥ fetch_b → combine`

Mixed (explicit deps on prior step):

```yaml
steps:
  - id: validate_events
    uses: data.schema.validate
  - id: analyze_trace
    uses: ops.trace.analyze
    config:
      depends_on: [validate_events]
  - id: monitor_trace
    uses: ops.trace.monitor
    config:
      depends_on: [analyze_trace]
```

Execution order: `validate_events → analyze_trace → monitor_trace`

## Thread Safety

The scheduler uses `ThreadPoolExecutor` for parallel step execution.
All mutations to shared `ExecutionState` (vars, outputs, events) are serialized
through `_StateLock`, which is attached to the execution context.

Key invariant: capability execution (LLM calls, HTTP requests, etc.) runs
outside the lock. Only state mutations are serialized.

## Failure Handling

- If a step fails and `fail_fast=True` (default), all pending futures are
  cancelled and execution returns immediately.
- If a step fails and `fail_fast=False`, steps that depend on the failed step
  are marked as `skipped` with `error_message: "Skipped: dependency failed"`.
  Independent steps continue executing.
- Circular or unsatisfied dependencies raise a `RuntimeError` with a deadlock
  message listing the unresolved steps.

## Validation

The scheduler validates that all `depends_on` references point to existing
step IDs. An `InvalidSkillSpecError` is raised for unknown step references.

## Configuration

- `max_workers`: maximum parallel threads (default: 8).
- The scheduler is instantiated by `ExecutionEngine` and used automatically
  for all skill executions.

## Testing

- `runtime/test_scheduler_functional.py`: 5 functional tests covering
  sequential, parallel, mixed, and single-step scenarios.
- `runtime/test_scheduler_stress.py`: 5 stress tests covering fan-out,
  deep chains, diamond patterns, and concurrent safety.

## Related Docs

- [RUNNER_GUIDE.md](RUNNER_GUIDE.md): end-to-end execution flow
- [SKILL_FORMAT.md](../agent-skill-registry/docs/SKILL_FORMAT.md): `config.depends_on` field spec
- [OBSERVABILITY.md](OBSERVABILITY.md): step-level event tracing

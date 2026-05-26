# RFC-0004: Runtime APIs and Event Contract

Status: Draft
Date: 2026-05-26
Depends on: docs/rfcs/RFC-0001-ORCA-RUNTIME-BLUEPRINT.md

## 1. Scope

Define stable runtime surface contracts for:

1. Python API.
2. HTTP API.
3. Event streaming contract.

## 2. Python API Target

```python
runtime = OrcaRuntime.from_paths(
    skills_path="skills/",
    bindings_path="bindings/",
    services_path="services/",
)

result = runtime.run("decision.make", inputs={...}, options={...})
result = await runtime.arun("decision.make", inputs={...}, options={...})

runtime.resume(run_id="run_...")
runtime.replay(run_id="run_...", from_step="score_options")
runtime.fork(run_id="run_...", from_checkpoint="chk_004")

runtime.approve(run_id="run_...", step_id="send_email", approver="alice")
runtime.deny(run_id="run_...", step_id="send_email", reason="wrong recipient")

async for event in runtime.astream(run_id="run_..."):
    ...
```

## 3. HTTP API Target

### 3.1 Run lifecycle

1. POST /v1/runs
2. GET /v1/runs/{run_id}
3. POST /v1/runs/{run_id}/resume
4. POST /v1/runs/{run_id}/replay
5. POST /v1/runs/{run_id}/fork
6. POST /v1/runs/{run_id}/cancel

### 3.2 Human-in-the-loop

1. POST /v1/runs/{run_id}/approve
2. POST /v1/runs/{run_id}/deny

### 3.3 Trace/checkpoint/events

1. GET /v1/runs/{run_id}/trace
2. GET /v1/runs/{run_id}/events
3. GET /v1/runs/{run_id}/checkpoints
4. GET /v1/runs/{run_id}/stream

## 4. Event Contract

Mandatory fields:

1. event_id
2. event_version
3. event_type
4. occurred_at
5. run_id
6. trace_id
7. payload

Example:

```json
{
  "event_id": "evt_01J...",
  "event_version": "1.0",
  "event_type": "step.completed",
  "occurred_at": "2026-05-26T12:00:05Z",
  "run_id": "run_01J...",
  "trace_id": "trc_...",
  "payload": {
    "step_id": "score_options",
    "duration_ms": 842,
    "checkpoint_id": "chk_004"
  }
}
```

## 5. Event Types (v1)

1. run.started
2. run.resumed
3. run.waiting_for_human
4. run.completed
5. run.failed
6. step.started
7. step.completed
8. capability.selected
9. binding.attempted
10. side_effect.recorded
11. side_effect.reused
12. checkpoint.saved

## 6. Compatibility Rules

1. EventStore contract is canonical source of runtime truth.
2. Existing log event names remain as projection during migration.
3. Existing HTTP routes remain available during migration window.
4. New routes are additive now and become preferred contract immediately.
5. Legacy routes/payload shapes are retired according to RFC-0006.

## 7. Collision Notes and Decision Proposals

1. Current /v1/runs payload is minimal and async-poll oriented.
Decision: extend payload with additive fields (status detail, checkpoint_head, waiting context) while preserving existing fields during migration.

2. Current streaming exists for execute/stream callbacks but not canonical run event streams.
Decision: preserve execute/stream temporarily and add run-scoped stream endpoint as canonical streaming surface.

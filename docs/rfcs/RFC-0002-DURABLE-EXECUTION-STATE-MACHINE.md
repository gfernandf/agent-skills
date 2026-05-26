# RFC-0002: Durable Execution State Machine

Status: Draft
Date: 2026-05-26
Depends on: docs/rfcs/RFC-0001-ORCA-RUNTIME-BLUEPRINT.md

## 1. Scope

Define canonical run lifecycle semantics for durable execution:

1. Run status model.
2. Allowed state transitions.
3. Checkpoint boundaries.
4. Resume/replay/fork semantics.

## 2. Canonical Run Statuses

1. pending
2. running
3. waiting_for_human
4. waiting_for_signal
5. replaying
6. completed
7. failed
8. canceled

## 3. Transition Rules

Allowed transitions:

1. pending -> running
2. running -> waiting_for_human
3. waiting_for_human -> running
4. running -> waiting_for_signal
5. waiting_for_signal -> running
6. running -> replaying
7. replaying -> running
8. running -> completed
9. running -> failed
10. running -> canceled
11. replaying -> failed
12. replaying -> canceled

Terminal states:

1. completed
2. failed
3. canceled

## 4. Checkpoint Boundary Policy

Checkpoint creation is mandatory at these boundaries:

1. Run started.
2. Step completed (including degraded and skipped).
3. Transition to waiting_for_human.
4. Transition to waiting_for_signal.
5. Run finished (completed, failed, canceled).

Checkpoint creation is optional at these boundaries:

1. Step started.
2. Retry scheduled.

Rationale: keep durable semantics strong while avoiding unnecessary persistence overhead.

## 5. RunStore v2 Shape

Minimum fields:

1. run_id
2. thread_id
3. skill_id
4. skill_version
5. status
6. created_at
7. started_at
8. finished_at
9. current_step_id
10. checkpoint_head
11. resume_from_checkpoint_id
12. trace_id
13. tenant_id
14. environment
15. versions.capabilities
16. versions.bindings
17. versions.registry_ref
18. policy_snapshot_id

Compatibility note: existing fields (result/error/status) remain populated during migration, but RunStore v2 is the canonical internal model.

## 6. Resume Semantics

Resume preconditions:

1. run.status in {waiting_for_human, waiting_for_signal, failed, canceled}.
2. checkpoint_head exists.
3. policy re-evaluation succeeds unless forced recovery mode is explicitly enabled.

Resume behavior:

1. Load checkpoint_head snapshot into execution state.
2. Transition run to running.
3. Emit run.resumed event.
4. Continue scheduler from next eligible step boundary.

## 7. Replay Semantics

Replay behavior:

1. Build a new run with source_run_id and replay metadata.
2. Start from selected checkpoint or step boundary.
3. Execute under replay policy for side effects.
4. Record replay lineage (source run and source checkpoint).

Replay is never in-place mutation of an existing run.

## 8. Fork Semantics

Fork behavior:

1. Clone a run from a selected checkpoint.
2. Assign new run_id.
3. Preserve source linkage metadata.
4. Allow different runtime options/policies unless restricted by environment policy.

## 9. Collision Notes and Decision Proposals

1. Current run status model in docs/ASYNC_EXECUTION.md supports running/completed/failed only.
Decision: canonical runtime status model is adopted now; legacy response shape is a temporary projection layer.

2. Current run_store.py stores minimal execution metadata.
Decision: RunStoreV2 replaces authoritative run state. Existing RunStore methods are compatibility wrappers only.

3. Current checkpoint.py serializes state but has no lifecycle orchestration.
Decision: CheckpointManager becomes mandatory lifecycle component and wraps existing serializer with versioned upgrade path.

## 10. Legacy Compatibility Window

1. Compatibility layer remains only for migration releases.
2. New run lifecycle features are not implemented on legacy-only structures.
3. Retirement criteria are defined in RFC-0006.

## 11. Validation Scenarios

1. Pause for confirmation and resume to completion.
2. Replay from step boundary using recorded side-effect results.
3. Fork from checkpoint and run with modified non-breaking options.
4. Canonical run status is exposed consistently across Python and HTTP runtime APIs.

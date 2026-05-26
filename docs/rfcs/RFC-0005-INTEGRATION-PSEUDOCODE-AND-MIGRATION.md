# RFC-0005: Integration Pseudocode and Migration

Status: Draft
Date: 2026-05-26
Depends on: RFC-0001 through RFC-0004

## 1. Purpose

Provide an intermediate pseudocode layer before production implementation.

Goals:

1. Validate integration semantics with current runtime.
2. Make hidden collisions explicit before code churn.
3. Keep migration incremental with explicit hard cutover and retirement.

## 2. Interfaces

```python
class RunStoreV2:
    def create_run(self, run: dict) -> dict: ...
    def get_run(self, run_id: str) -> dict | None: ...
    def update_status(self, run_id: str, status: str, **fields) -> None: ...
    def patch_run(self, run_id: str, fields: dict) -> None: ...

class CheckpointStore:
    def save_checkpoint(self, checkpoint: dict, state_snapshot: dict) -> str: ...
    def load_checkpoint(self, run_id: str, checkpoint_id: str | None = None) -> dict | None: ...
    def list_checkpoints(self, run_id: str) -> list[dict]: ...

class EventStore:
    def append(self, event: dict) -> None: ...
    def list_events(self, run_id: str, cursor: str | None = None, limit: int = 100) -> list[dict]: ...

class SideEffectLedger:
    def find_by_idempotency_key(self, key: str) -> dict | None: ...
    def record_attempt(self, record: dict) -> str: ...
    def record_result(self, effect_id: str, result: dict) -> None: ...
```

## 3. Durable Execution Loop (Pseudocode)

```python
def execute_run(run_id: str):
    run = run_store_v2.get_run(run_id)
    state = checkpoint_store.load_checkpoint(run_id, run.get("checkpoint_head"))
    if state is None:
        state = create_initial_state(run)

    emit_event("run.started", run, state)
    run_store_v2.update_status(run_id, "running")

    while not is_terminal_state(state):
        step = scheduler_next_step(state)
        if step is None:
            break

        emit_event("step.started", run, state, step=step)

        policy_decision = policy_manager.evaluate(state, step)
        if policy_decision.requires_human:
            checkpoint_id = checkpoint_boundary(
                run,
                state,
                step,
                kind="waiting_for_human",
            )
            run_store_v2.update_status(
                run_id,
                "waiting_for_human",
                current_step_id=step.id,
                checkpoint_head=checkpoint_id,
            )
            emit_event("run.waiting_for_human", run, state, step=step)
            return

        step_result = execute_step_with_effect_safety(run, state, step)
        apply_step_result(state, step_result)

        checkpoint_id = checkpoint_boundary(run, state, step, kind="step_completed")
        run_store_v2.patch_run(
            run_id,
            {
                "current_step_id": step.id,
                "checkpoint_head": checkpoint_id,
            },
        )
        emit_event("step.completed", run, state, step=step)

    finalize_status = derive_final_status(state)
    run_store_v2.update_status(run_id, finalize_status)
    emit_event(f"run.{finalize_status}", run, state)
```

## 4. Side-Effect Safety (Pseudocode)

```python
def execute_step_with_effect_safety(run: dict, state: dict, step: dict):
    if not is_side_effecting(step):
        return binding_executor.execute(step)

    idem_key = build_idempotency_key(run, step, state)
    previous = side_effect_ledger.find_by_idempotency_key(idem_key)
    replay_policy = resolve_replay_policy(step)

    if previous and replay_policy == "use_recorded_result":
        emit_event("side_effect.reused", run, state, step=step, effect_id=previous["effect_id"])
        return load_recorded_result(previous)

    if previous and replay_policy == "require_human":
        raise RuntimeNeedsHumanApproval(step_id=step["id"], reason="side_effect_replay")

    effect_id = side_effect_ledger.record_attempt(
        {
            "run_id": run["run_id"],
            "step_id": step["id"],
            "idempotency_key": idem_key,
            "request_hash": hash_request(step),
            "replay_policy": replay_policy,
        }
    )

    result = binding_executor.execute(step)
    side_effect_ledger.record_result(effect_id, result)
    emit_event("side_effect.recorded", run, state, step=step, effect_id=effect_id)
    return result
```

## 5. Migration Order

1. Introduce RunStoreV2 as canonical run persistence and wrap existing run_store calls as compatibility shims.
2. Introduce CheckpointManager around existing checkpoint serializer and enforce boundary policy.
3. Add state-machine enforcement and waiting_for_human status as canonical lifecycle behavior.
4. Add SideEffectLedger and idempotency policy evaluation in canonical execution path.
5. Add runtime APIs for resume/replay/fork/approve/deny and route them to canonical core.
6. Add EventStore canonical events and treat log events as projections.
7. Perform hard cutover to canonical async core.
8. Retire legacy execution path, legacy run model, and legacy-only event semantics.

## 6. Adopted Architectural Decisions

1. Async core is canonical target architecture.
2. Legacy /v1/skills/{id}/execute/async compatibility exists only during migration window.
3. use_recorded_result is default replay policy for external_action side effects.
4. EventStore is canonical truth; observability logs are projections.
5. Checkpoint serialization remains backward compatible via versioned upgrades.
6. Legacy components are retired after cutover gates in RFC-0006.

## 7. Exit Criteria for Design Phase

Design phase is complete when:

1. RFC-0001 to RFC-0005 are accepted for implementation.
2. Implementation slicing and cutover gates are agreed.
3. Legacy retirement matrix (RFC-0006) is accepted.

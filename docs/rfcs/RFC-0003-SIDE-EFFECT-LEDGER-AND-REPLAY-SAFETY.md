# RFC-0003: Side-Effect Ledger and Replay Safety

Status: Draft
Date: 2026-05-26
Depends on: docs/rfcs/RFC-0001-ORCA-RUNTIME-BLUEPRINT.md, docs/rfcs/RFC-0002-DURABLE-EXECUTION-STATE-MACHINE.md

## 1. Problem

Durable execution is unsafe if replay/resume can duplicate external actions.

Examples of unsafe duplication:

1. Duplicate outbound email.
2. Duplicate ticket creation.
3. Duplicate payment or irreversible command.

## 2. Capability and Binding Semantics

### 2.1 Capability Runtime Fields

1. side_effects: none | read | write | external_action
2. idempotency: required | optional | not_supported
3. replay_policy: use_recorded_result | reexecute | require_human

### 2.2 Binding Runtime Fields

1. binding_call_id
2. idempotency_key
3. request_hash
4. response_hash
5. side_effect_status

Compatibility note: existing properties in capability specs remain valid; runtime semantics are canonical in SideEffectLedger during migration and after cutover.

## 3. SideEffectRecord

Minimum record shape:

1. effect_id
2. run_id
3. step_id
4. capability_id
5. binding_id
6. effect_class
7. idempotency_key
8. request_hash
9. response_hash
10. status (attempted, recorded, reused, blocked, failed)
11. replay_policy
12. recorded_result_ref
13. created_at
14. updated_at

## 4. Replay Policies

1. use_recorded_result
Behavior: if idempotency key exists, return recorded result without external re-execution.

2. reexecute
Behavior: execute external action again; create a new effect record.

3. require_human
Behavior: transition run to waiting_for_human before external re-execution.

Default policy for external_action: use_recorded_result.

## 5. Integration Point in Execution Flow

SideEffectManager is called at step execution boundary when selected binding is side-effecting.

Order:

1. Build idempotency key.
2. Check ledger for existing matching entry.
3. Apply replay policy.
4. Execute or reuse.
5. Record outcome and hashes.

## 6. Hashing Rules

1. request_hash computed from normalized request payload.
2. response_hash computed from normalized response payload when available.
3. Hash function default: sha256.

## 7. Collision Notes and Decision Proposals

1. Current runtime binding metadata includes attempts and fallback metadata but no durable effect ledger.
Decision: keep existing step metadata and append side_effect metadata references; SideEffectLedger becomes authoritative for effect history.

2. Current safety model uses requires_confirmation at capability level.
Decision: integrate require_human replay policy with existing confirmation model; no separate non-durable behavior path after cutover.

3. Current audit records already include hashed step input/output snapshots.
Decision: link audit records to SideEffectRecord IDs for cross-reference.

## 8. Acceptance Criteria

1. Replay does not duplicate side effects under default policy.
2. Operators can trace exactly when an effect was executed versus reused.
3. Human approval boundary can be inserted before side-effect re-execution.

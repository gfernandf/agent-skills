# Durability Contract (v1)

Status: Active baseline
Last updated: 2026-05-28

This document formalizes the current ORCA durability baseline so it is testable,
reviewable, and safe to evolve.

## Scope

Durability contract v1 covers:

1. Checkpoint state persistence and load semantics.
2. Run lifecycle durability transitions for resume/replay/fork flows.
3. Backward-compatible behavior of customer-facing run durability endpoints.

## Contract Invariants

1. Checkpoint round-trip preserves ExecutionState fields required for safe continuation.
2. Resume uses a valid checkpoint as source-of-truth for continuation state.
3. Replay creates a new run identity and executes from checkpoint-derived state.
4. Fork creates a new pending run identity pointing to a selected checkpoint.
5. Missing checkpoint/run references fail deterministically with typed not-found semantics.
6. Durability flows do not mutate capability contract definitions.

## Required Runtime Operations

1. Save checkpoint record + state snapshot.
2. Load checkpoint record + state snapshot.
3. List run checkpoints.
4. Resume run from checkpoint.
5. Replay run from checkpoint.
6. Fork run from checkpoint.

## Verification Baseline

Run the durability contract verifier:

```bash
python tooling/verify_durability_contract.py --report-file artifacts/durability_contract_report.json
```

The verifier executes canonical test nodes for:

1. `runtime/test_checkpoint.py`
2. `runtime/test_checkpoint_manager.py`
3. `runtime/test_run_store.py`
4. resume/replay/fork integration slices in `test_neutral_api_slice2.py`

## CI Integration

Durability contract report artifact:

1. `artifacts/durability_contract_report.json`
2. `artifacts/durability_advanced_report.json`

Advanced durability verifier (v2 baseline+):

```bash
python tooling/verify_durability_advanced.py --report-file artifacts/durability_advanced_report.json
```

The advanced verifier covers grouped scenarios for:

1. restart continuity
2. replay equivalence
3. failure-injection durability paths

Expected summary fields:

1. `status`
2. `summary.total/passed/failed/pass_ratio`
3. `tests[]`
4. `failures[]`

Expected advanced summary fields:

1. `status`
2. `summary.total_scenarios/passed_scenarios/failed_scenarios/scenario_pass_ratio`
3. `scenarios[]`
4. `failures[]`

## Out of Scope (v1)

1. Temporal-native orchestration semantics.
2. Cross-process distributed workflow history store.
3. Side-effect ledger guarantees beyond existing replay/fork lifecycle behavior.

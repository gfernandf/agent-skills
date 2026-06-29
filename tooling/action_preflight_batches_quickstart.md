# Action Preflight Batches - Quickstart

Goal: run 3 cases per batch with clear pass/fail criteria and strict gating.

## Files
- Manifest: tooling/action_preflight_batches_manifest.json
- Cases: test_inputs/action_preflight_batch_cases.json
- Runner: tooling/run_action_preflight_batches.py
- Reports: artifacts/action_preflight_batches/

## Execution Modes

1. Run one batch
- Command:
  - python tooling/run_action_preflight_batches.py --batch <ID>
- Exit code:
  - 0 = batch passed
  - 1 = batch failed (iterate on skill)

2. Run sequentially with stop on failure
- Command:
  - python tooling/run_action_preflight_batches.py --until-fail --start-batch <ID>
- Behavior:
  - Pass batch -> continue next batch
  - Fail batch -> stop immediately

## Batch Map (3 cases each)
- Batch 0: preflight checks (skill/capabilities/tenant gate)
- Batch 1: smoke functional (low/medium/high canonical)
- Batch 2: determinism stability (same 3 cases, repeats=3)
- Batch 3: adversarial inputs
- Batch 4: resilience set
- Batch 5: regression compact set

## Criteria (enforced by runner)
- required_pass_rate
- max_errors
- max_fallback_ratio (if configured)
- forbid_unsafe_proceed_medium_high
- max_decision_variants_per_case (for determinism batch)

## Suggested Iterative Workflow
1. Run Batch 0.
2. If pass, run Batch 1.
3. If fail, iterate on skill, then rerun only failed batch.
4. Continue Batch 2 -> 3 -> 4 -> 5 with same rule.

## Report Reading
Each batch writes JSON report with:
- status: passed|failed
- go_no_go: go|no_go
- summary: pass_rate/errors/fallback_ratio/unsafe_proceed
- per-case results and decisions

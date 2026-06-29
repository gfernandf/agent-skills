# Batch A Protocol Freeze - Action Preflight Forecast Study

Status: Approved and closed (executed through Batch F reproducibility package)
Date: 2026-06-29
Owners: agent-skills team

## 1. Study Goal
Evaluate whether the `decision.action-preflight-forecast` skill improves decision quality under uncertainty and operational pressure while avoiding over-reliance on rigid guardrails.

Primary claim:
- Structured forecast signals (risk, uncertainty, reversibility, privacy, incident pressure, operating environment) reduce unsafe decisions in medium/high risk scenarios.

## 2. Scope and Frozen Components
Frozen for this study batch:
- Skill: `decision.action-preflight-forecast`
- Main runtime repo: `agent-skills`
- Registry repo: `agent-skill-registry`
- Batch runner: `tooling/run_action_preflight_batches.py`
- Base case set: `test_inputs/action_preflight_batch_cases.json`
- Base batch manifest: `tooling/action_preflight_batches_manifest.json`

Freeze policy:
- Any logic change after freeze requires a new run ID and explicit changelog entry.
- No threshold retuning is allowed inside a run ID after first benchmark execution.

## 3. Risk Families Included
1. Low-risk reversible operations.
2. Medium-risk ambiguous operations.
3. High-risk operational actions with rollback constraints.
4. Sensitive-data and privacy-scoped operations.
5. Incident/hotfix pressure scenarios.
6. Binding-resilience scenarios with partial/incomplete evidence.
7. Regression pack scenarios.

## 4. Primary Endpoints (Pre-registered)
Primary endpoints:
- Decision family accuracy.
- Unsafe proceed rate in medium/high risk bands.
- Batch pass rate under frozen criteria.

Secondary endpoints:
- Fallback ratio (execution quality indicator, not direct decision quality).
- Determinism (decision variants per case across repeats).
- Must-detect term coverage.
- Execution error rate.

## 5. Acceptance Gates for Batch A
Batch A is complete when all of the following are reviewed and approved:
- Protocol approved (this file).
- Evaluation manifest approved (`BATCH_BF_EVALUATION_MANIFEST.json`).
- Report schema template approved (`REPORT_TEMPLATE.md`).
- Case freeze hash recorded in run ledger (to be generated in Batch B kickoff).

## 6. Threats to Validity (Declared Upfront)
- Distribution bias in curated case packs.
- Overfitting to known batch criteria.
- Runtime/provider drift effects on fallback behavior.
- Confidence score calibration sensitivity.

Mitigation plan:
- Holdout family expansion in later batch.
- Ablation study with explicit component removals.
- Versioned runtime + manifest + case freeze hash.

## 7. Reproducibility Requirements
Every run must log:
- Runtime commit hash.
- Registry commit hash.
- Runner script hash.
- Manifest hash.
- Case file hash.
- Execution timestamp UTC.
- Environment stamp (python version, OS, critical env vars redacted).

## 8. Batch-by-Batch Execution Plan (for later stages)
- Batch B: Core benchmark vs current frozen criteria.
- Batch C: Ablations per major signal family.
- Batch D: Robustness and adversarial perturbations.
- Batch E: Calibration and reliability analysis.
- Batch F: External reproducibility package.

## 9. Review Checklist
- [ ] Endpoints and hypotheses accepted.
- [ ] Family taxonomy accepted.
- [ ] Freeze policy accepted.
- [ ] Evidence artifacts accepted.
- [ ] Go/no-go criteria accepted.

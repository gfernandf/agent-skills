# External Validation Checklist (10 Minutes)

Use this checklist to independently verify the frozen release of:
- decision.action-preflight-forecast

## 1. Repository and Commit Pinning
- [ ] Clone both repositories side by side: agent-skills and agent-skill-registry
- [ ] Checkout agent-skills commit: c41e701980957b4552c90b76e4eab2ced8bf1b82
- [ ] Checkout agent-skill-registry commit: 043b35a1cb2477198833217ee4653cc9039c1928

## 2. Skill Freeze Integrity
- [ ] Confirm skill file exists: skills/official/decision/action-preflight-forecast/skill.yaml
- [ ] Compute SHA-256 of that file
- [ ] Confirm hash equals: 2fb79c6e7dcca5f84a97ffb8f1c9e50c9ac545186a01c804f7bba2fe6c6e27ed

## 3. Runtime Sanity
- [ ] Run bootstrap/install for local environment
- [ ] Run runtime doctor check (python skills.py doctor)
- [ ] Confirm no blocking runtime errors

## 4. Reproducibility Package Completeness
- [ ] Open package root: artifacts/paper_runs/F_reproducibility_run1/
- [ ] Confirm file present: run_manifest.json
- [ ] Confirm file present: frozen_inputs_hashes.json
- [ ] Confirm file present: raw_reports_bundle.json
- [ ] Confirm file present: aggregated_tables_bundle.json
- [ ] Confirm file present: figure_specs.json
- [ ] Confirm file present: package_index.json

## 5. Report Consistency
- [ ] Final report exists: docs/papers/action_preflight_forecast_study/BATCH_BF_FINAL_REPORT.md
- [ ] Master manifest exists: docs/papers/action_preflight_forecast_study/BATCH_BF_EVALUATION_MANIFEST.json
- [ ] External guide exists: docs/ACTION_PREFLIGHT_FORECAST_EXTERNAL.md
- [ ] Metrics in report and manifest are consistent for B, D, E, F

## 6. Go/No-Go Sanity Checks
- [ ] Batch B marked GO
- [ ] Batch D unsafe_proceed_under_stress equals 0
- [ ] Batch E overconfidence_rate equals 0.0
- [ ] Batch F missing_artifacts is empty

## 7. Sign-off Record
- Reviewer:
- Date:
- Result (PASS/FAIL):
- Notes:

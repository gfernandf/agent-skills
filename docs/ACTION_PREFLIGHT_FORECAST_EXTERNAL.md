# External Use Guide: decision.action-preflight-forecast (Frozen)

This guide documents the frozen, externally reproducible package for the skill:
- decision.action-preflight-forecast

## 1. Freeze Record
- Study ID: action_preflight_forecast_journal_2026
- Freeze status: batch_f_completed
- Runtime repo commit (agent-skills): c41e701980957b4552c90b76e4eab2ced8bf1b82
- Registry repo commit (agent-skill-registry): 043b35a1cb2477198833217ee4653cc9039c1928
- Frozen skill file:
  - skills/official/decision/action-preflight-forecast/skill.yaml
  - SHA-256: 2fb79c6e7dcca5f84a97ffb8f1c9e50c9ac545186a01c804f7bba2fe6c6e27ed

## 2. Canonical Contracts and Scope
- Capability contracts remain canonical and stable.
- OpenAPI is preferred when available; fallback behavior is tracked as execution quality, not automatic decision-quality failure.
- No post-freeze threshold retuning was applied within the frozen run lineage.

## 3. Reproducibility Package
Use the Batch F package:
- artifacts/paper_runs/F_reproducibility_run1/

Included outputs:
- run_manifest.json
- frozen_inputs_hashes.json
- raw_reports_bundle.json
- aggregated_tables_bundle.json
- figure_specs.json
- package_index.json

## 4. Minimal External Reproduction Steps
1. Clone both repositories side by side:
- agent-skills
- agent-skill-registry

2. Pin exact commits:
- agent-skills: c41e701980957b4552c90b76e4eab2ced8bf1b82
- agent-skill-registry: 043b35a1cb2477198833217ee4653cc9039c1928

3. Setup and validate:
- make bootstrap
- python skills.py doctor

4. Verify frozen package integrity:
- Compare hashes in artifacts/paper_runs/F_reproducibility_run1/frozen_inputs_hashes.json
- Validate referenced raw reports in artifacts/paper_runs/F_reproducibility_run1/raw_reports_bundle.json

5. Re-run paper manifests if needed:
- python tooling/prepare_paper_run_manifest.py --batch-label B --run-label external_recheck_b
- python tooling/prepare_paper_run_manifest.py --batch-label C --run-label external_recheck_c
- python tooling/prepare_paper_run_manifest.py --batch-label D --run-label external_recheck_d
- python tooling/prepare_paper_run_manifest.py --batch-label E --run-label external_recheck_e
- python tooling/prepare_paper_run_manifest.py --batch-label F --run-label external_recheck_f

## 5. Batch Status Summary
- Batch B: passed/go
- Batch C: completed (expected ablation degradations documented)
- Batch D: completed, robust_pass_rate 0.9667, unsafe_proceed_under_stress 0
- Batch E: completed, brier_score 0.0064, ece 0.08, overconfidence_rate 0.0
- Batch F: completed, packaging incidents 0, missing artifacts 0

## 6. Primary References
- docs/papers/action_preflight_forecast_study/BATCH_A_PROTOCOL.md
- docs/papers/action_preflight_forecast_study/BATCH_BF_EVALUATION_MANIFEST.json
- docs/papers/action_preflight_forecast_study/BATCH_BF_FINAL_REPORT.md
- artifacts/paper_runs/F_reproducibility_run1/package_index.json

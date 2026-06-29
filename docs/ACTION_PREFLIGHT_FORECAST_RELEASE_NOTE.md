# Release Note: decision.action-preflight-forecast (Frozen External Package)

## Release Summary
This release publishes a frozen, externally reproducible package for:
- decision.action-preflight-forecast

Publication status:
- Approved and closed through Batch F reproducibility.
- Intended for external validation and controlled adoption.

## Version Pins and Freeze Proof
- Runtime repository (agent-skills): c41e701980957b4552c90b76e4eab2ced8bf1b82
- Registry repository (agent-skill-registry): 043b35a1cb2477198833217ee4653cc9039c1928
- Frozen skill path: skills/official/decision/action-preflight-forecast/skill.yaml
- Frozen skill SHA-256: 2fb79c6e7dcca5f84a97ffb8f1c9e50c9ac545186a01c804f7bba2fe6c6e27ed

## Quality Outcome (B-F)
- Batch B (core benchmark): GO (all batches passed)
- Batch C (ablation): completed; expected degradations documented
- Batch D (robustness): robust_pass_rate 0.9667, unsafe_proceed_under_stress 0
- Batch E (calibration): brier_score 0.0064, ece 0.08, overconfidence_rate 0.0
- Batch F (repro package): complete, no missing artifacts

## External Consumption Entry Points
- External guide: docs/ACTION_PREFLIGHT_FORECAST_EXTERNAL.md
- Final report: docs/papers/action_preflight_forecast_study/BATCH_BF_FINAL_REPORT.md
- Master manifest: docs/papers/action_preflight_forecast_study/BATCH_BF_EVALUATION_MANIFEST.json
- Repro package index: artifacts/paper_runs/F_reproducibility_run1/package_index.json

## Scope and Guardrails
- Capability contracts remain canonical and stable.
- No post-freeze threshold retuning is part of this release lineage.
- This release is traceable by pinned commits and frozen artifact hashes.

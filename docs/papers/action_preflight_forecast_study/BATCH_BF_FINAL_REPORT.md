# Action Preflight Forecast Study - Final Report (B-F)

## 1. Run Metadata
- Study ID: action_preflight_forecast_journal_2026
- Freeze run: run0_freeze
- Final status: batch_f_completed
- Final package run: reproducibility_run1
- Runtime commit (agent-skills): c41e701980957b4552c90b76e4eab2ced8bf1b82
- Registry commit (agent-skill-registry): 043b35a1cb2477198833217ee4653cc9039c1928
- Frozen case hash: f6b83e35cff53bff8b4faa254554256df3ee94bfb3edcb9f672d0afec375cf42
- Frozen batch-manifest hash: 68d817771d72d54aea7075ee89d67a4e890b62ba2423983bb1770e7bd473bcb8
- Frozen runner hash: 496de4e2230b3017707d28f97d24e2f66929db648f814b2ee215845d6f3792b1
- Platform: Windows-11-10.0.26100-SP0
- Python: 3.14.3 (AMD64)

## 2. Experimental Configuration
- Frozen skill under test: decision.action-preflight-forecast
- Core benchmark batches: 1, 2, 3, 4, 5
- Ablation variants: full_skill, minus_privacy_signal, minus_incident_pressure_signal, minus_rollback_signal, minus_uncertainty_extraction, minus_enriched_branch_logic
- Robustness perturbations: paraphrase, signal_dropout, conflicting_constraints, incomplete_context
- Calibration stratification: risk_band, family, execution_health
- Threshold retuning after freeze: none

## 3. Batch B - Core Benchmark
All five core batches passed with go/no-go = go.

| Batch | Pass rate | Errors | Unsafe proceed medium/high | Fallback ratio | Result |
|---|---:|---:|---:|---:|---|
| 1 smoke_functional | 1.0 | 0 | 0 | 0.3333 | go |
| 2 determinism_stability | 1.0 | 0 | 0 | 0.1111 | go |
| 3 adversarial_inputs | 1.0 | 0 | 0 | 0.0 | go |
| 4 binding_resilience | 1.0 | 0 | 0 | 0.0 | go |
| 5 regression_pack | 1.0 | 0 | 0 | 0.3333 | go |

## 4. Batch C - Ablation Suite
Ablations were evaluated against full_skill deltas (not treated as operational incidents).

Key findings:
- minus_uncertainty_extraction produced the largest degradation: delta_pass_rate = -0.6667 across B1-B5 and unsafe decision drift in multiple batches.
- minus_privacy_signal degraded batch 3 (delta_pass_rate = -0.3333).
- minus_enriched_branch_logic degraded batch 3 (delta_pass_rate = -0.3333).
- minus_incident_pressure_signal and minus_rollback_signal showed no degradation on this frozen set.

Interpretation:
- Uncertainty extraction is a dominant contributor to safe continuation behavior.
- Privacy and enriched branch logic provide targeted robustness in adversarial/sensitive scenarios.

## 5. Batch D - Robustness/Adversarial
Summary:
- robust_pass_rate: 0.9667
- error_rate: 0.0
- unsafe_proceed_under_stress: 0
- decision_stability_under_perturbation: 0.9792
- fallback_ratio: 0.0333

Perturbation-level note:
- incomplete_context reduced pass_rate to 0.8333 while preserving unsafe_proceed_medium_high = 0.

## 6. Batch E - Calibration/Reliability
Summary:
- accuracy: 1.0
- avg_confidence: 0.92
- brier_score: 0.0064
- ece: 0.08
- overconfidence_rate: 0.0
- error_rate: 0.0

Reliability note:
- Confidence mass is concentrated in the 0.9-1.0 bin for this frozen set.

## 7. Batch F - Reproducibility Package
Batch F produced a complete external-ready package with no missing artifacts:
- run_manifest.json
- frozen_inputs_hashes.json
- raw_reports_bundle.json
- aggregated_tables_bundle.json
- figure_specs.json

Package root:
- artifacts/paper_runs/F_reproducibility_run1/

## 8. Error Taxonomy and Incidents
- Operational incidents: 0 (B, C, D, E, F)
- Packaging incidents: 0
- Missing artifacts: 0
- Observed degradations in C are experimental findings by design, not runtime failures.

## 9. Go/No-Go Decision
- Decision: GO
- Reasoning summary:
  - Baseline skill meets all frozen quality/safety criteria (Batch B).
  - Robustness remains high under perturbations (Batch D) with zero unsafe-proceed events in medium/high risk bands.
  - Confidence quality is strong on this frozen benchmark set (Batch E).
  - Reproducibility package is complete and hash-traceable (Batch F).

## 10. Reproducibility Artifacts
- Master manifest: docs/papers/action_preflight_forecast_study/BATCH_BF_EVALUATION_MANIFEST.json
- Batch B run manifest: artifacts/paper_runs/B_core_benchmark_run1_run_manifest.json
- Batch C run manifest: artifacts/paper_runs/C_ablation_run1_run_manifest.json
- Batch D run manifest: artifacts/paper_runs/D_robustness_run1_run_manifest.json
- Batch E run manifest: artifacts/paper_runs/E_calibration_run1_run_manifest.json
- Batch F run manifest: artifacts/paper_runs/F_reproducibility_run1_run_manifest.json
- Final package index: artifacts/paper_runs/F_reproducibility_run1/package_index.json

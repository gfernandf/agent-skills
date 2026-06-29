# Action Preflight Forecast Study - Reporting Template

Use this template for each formal study run (Batch B-F).

## 1. Run Metadata
- Study ID:
- Batch ID:
- Run ID:
- UTC timestamp:
- Runtime commit:
- Registry commit:
- Runner hash:
- Manifest hash:
- Case file hash:
- Python version:
- OS:

## 2. Experimental Configuration
- Skill variant:
- Active batch IDs:
- Repeats:
- Criteria overrides (if any):
- Environment constraints (quota, provider state, etc):

## 3. Primary Results
| KPI | Value | Threshold | Pass/Fail |
|---|---:|---:|---|
| Pass rate |  |  |  |
| Decision family accuracy |  |  |  |
| Unsafe proceed medium/high |  |  |  |
| Error rate |  |  |  |

## 4. Secondary Results
| KPI | Value | Notes |
|---|---:|---|
| Fallback ratio |  |  |
| Determinism variants/case |  |  |
| Missing detect terms rate |  |  |
| Latency p50/p90 (optional) |  |  |

## 5. Family-Level Breakdown
| Family | Cases | Pass rate | Unsafe proceed | Key failure modes |
|---|---:|---:|---:|---|
| Low-risk reversible |  |  |  |  |
| Medium ambiguous |  |  |  |  |
| High operational |  |  |  |  |
| Sensitive/privacy |  |  |  |  |
| Incident/hotfix |  |  |  |  |
| Resilience/incomplete evidence |  |  |  |  |
| Regression pack |  |  |  |  |

## 6. Statistical Notes (journal-level)
- Confidence intervals (method):
- Significance tests (if applied):
- Effect sizes:
- Multiple-comparison correction:

## 7. Error Taxonomy
List each failure with:
- Case ID
- Risk band
- Expected family
- Observed decision
- Root cause class (logic, context propagation, fallback artifact, other)
- Corrective action

## 8. Reproducibility Artifacts
- Raw batch reports:
- Aggregated metrics JSON:
- Run logs:
- Environment stamp:
- Figure scripts/specs:

## 9. Go/No-Go Decision
- Decision:
- Reasoning summary:
- Follow-up actions:

## 10. Reviewer Sign-off
- Technical reviewer:
- Methodology reviewer:
- Date:

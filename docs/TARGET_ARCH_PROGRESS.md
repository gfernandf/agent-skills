# Target Architecture Progress Snapshot

Date: 2026-05-28
Source of criteria: docs/TARGET_ARCHITECTURE.md
Evidence anchors: docs/PROJECT_STATUS.md, runtime/tooling/docs state

## Method

1. Each Definition-of-Done criterion is scored in [0.0, 1.0].
2. Pillar % = average(criteria) * 100.
3. Overall % = average(pillar %).

This is a planning score, not a replacement for CI pass/fail gates.

## Pillar Scoring

### 1) Durability (Temporal-inspired)

Criteria scoring:

1. Survive restart without semantic drift: 0.60
2. Retry/timer/resume explicit and test-covered: 0.80
3. Checkpoint/replay API backward compatibility: 0.80

Pillar completion: 73%

Main gaps:

1. Durability contract baseline is now formalized and CI-verified, but workflow-history durability is not yet Temporal-grade.
2. Process restart continuity is covered at baseline level, but not yet expanded to full canonical durable orchestration semantics.

### 2) Contracts, Artifacts, Promotion (Dagster/dbt-inspired)

Criteria scoring:

1. Orchestrated reproducible pipeline stages: 0.60
2. Traceable lineage source -> artifacts: 0.50
3. CI/local equivalent governance outcomes: 0.80

Pillar completion: 63%

Main gaps:

1. Pipeline orchestration is strong but still custom-script centric.
2. End-to-end lineage is present in pieces, not yet unified as a first-class pipeline lineage model.

### 3) Policy and Tenancy (Kubernetes/OPA-inspired)

Criteria scoring:

1. Externally explainable and auditable policy decisions: 0.89
2. Tenant isolation consistency: 0.94
3. Existing runtime safety controls preserved: 0.90

Pillar completion: 92%

Main gaps:

1. OPA adapter wiring and tenant-scoped policy-bundle lifecycle verification are in place, including explicit environment promotion controls in manifest governance checks.
2. `same_tenant` runtime enforcement, 5-capability baseline rollout, channel-level probes, and HTTP/MCP transport probes are in place; broader registry rollout is still pending.

### 4) Developer Experience and Distribution (Stripe-like/Vercel-like)

Criteria scoring:

1. Time-to-first-success measured and improved: 0.55
2. Docs/examples parity-validated: 0.70
3. Environment promotion flow documented/reproducible: 0.50
4. OSS baseline without paid SaaS: 1.00

Pillar completion: 69%

Main gaps:

1. DX metrics trend and initial SLO evaluation are now in place, but thresholds still need progressive hardening.
2. Preview/promote environment UX is not yet formalized end-to-end.

## Overall Completion

Overall target architecture completion: 75%

Computation:

1. Durability: 73%
2. Contracts/artifacts/promotion: 63%
3. Policy/tenancy: 92%
4. DX/distribution: 69%
5. Overall average: 75%

## What Is Missing Next (Priority Order)

1. Temporal-grade durable orchestration layer beyond current durability contract baseline.
2. Orchestrated delivery lineage model for contract/artifact/promotion flow.
3. OPA staged enforcement policy hardening and CI/branch-level enforcement for environment promotion controls.
4. DX SLO hardening and deploy-flow latency instrumentation.

## Notes

1. LangGraph remains optional integration surface and is not scored as a mandatory core pillar.
2. Score reflects strategic target alignment, not capability coverage (which is already high).

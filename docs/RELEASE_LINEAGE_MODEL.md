# Release Lineage Model

Status: active
Last updated: 2026-05-28

This document defines the lineage artifact generated for release decisions.

## 1. Goal

Provide a single auditable graph that links:

1. Workflow source
2. Job outcomes
3. Produced artifacts
4. Final release decision

## 2. Artifact Outputs

Generated in the final release gate job:

1. `artifacts/release_lineage.json`
2. `artifacts/release_lineage.md`

Producer:

1. `tooling/generate_release_lineage.py`

## 3. Contract

Top-level contract id:

1. `release_lineage_v1`

Top-level fields:

1. `generated_at`
2. `contract`
3. `status`
4. `summary`
5. `lineage.nodes[]`
6. `lineage.edges[]`
7. `completeness_checks[]`

## 4. Node Types

Current node categories:

1. `source` (workflow origin)
2. `job` (GitHub Actions jobs)
3. `artifact` (JSON evidence files)
4. `decision` (final release decision)

## 5. Edge Semantics

Current edge relations:

1. `triggers` (source -> job)
2. `produces` (job -> artifact)
3. `drives` (artifact -> decision)

## 6. Completeness Checks

The lineage generator validates minimum completeness:

1. required jobs present in `needs`
2. required artifacts present in downloaded outputs
3. required lineage edges present

If `--fail-on-incomplete` is enabled, missing lineage elements fail the job.

## 7. Operational Use

Use lineage artifact for:

1. Release audit trail
2. Post-incident root-cause context
3. Evidence packaging in release notes

## 8. Related

1. `docs/PRODUCTION_READINESS.md`
2. `docs/PUBLIC_RELEASE_USE_CASES.md`
3. `docs/PRODUCT_100_EXECUTION_PLAN.md`
4. `tooling/generate_release_lineage.py`

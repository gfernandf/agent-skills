# Release Lineage Model

Status: active
Last updated: 2026-05-29

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
3. `artifacts/release_lineage_contract_report.json`

Producer:

1. `tooling/generate_release_lineage.py`
2. `tooling/verify_release_lineage_contract.py`

## 3. Contract

Top-level contract id:

1. `release_lineage_v1`
2. schema version `1.1` in `provenance.schema_version`

Top-level fields:

1. `generated_at`
2. `contract`
3. `status`
4. `provenance`
5. `summary`
6. `lineage.nodes[]`
7. `lineage.edges[]`
8. `completeness_checks[]`

`provenance` includes:

1. `schema_version`
2. `generator`
3. `source_workflow`
4. `artifacts_dir`
5. `required_jobs.total`
6. `required_jobs.present_in_needs`
7. `required_jobs.results`

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
4. node ids are unique
5. required node types are present
6. all edge endpoints reference existing nodes
7. release gate contract and decision/status are well-formed

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

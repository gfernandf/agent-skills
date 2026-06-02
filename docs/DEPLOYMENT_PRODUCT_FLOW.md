# Deployment Product Flow

Status: active
Last updated: 2026-05-29

This document defines the developer-facing deployment flow built on immutable
release bundles for local agent-skills instances.

This is pre-release documentation. It describes how the flow should work and
how it is verified, but it does not mean a public release should be executed
yet.

## 1. Goal

Provide a deployment experience that is:

1. Bundle-based and traceable
2. Preview-friendly for pull requests
3. Promotable across `preview -> dev -> staging -> prod`
4. Rollback-capable without ad hoc file surgery

This flow is intentionally local-instance compatible. Each deployed
agent-skills instance can build, verify, promote, and rollback its own bundle
without requiring a centralized runtime service.

## 2. Core Commands

Build a bundle from the current runtime, registry snapshot, and release evidence:

```bash
python skills.py release-bundle-build \
  --runtime-root . \
  --registry-root ../agent-skill-registry
```

Verify the manifest, required evidence files, and checksums:

```bash
python skills.py release-bundle-verify artifacts/release_bundles/<bundle-id>
```

Promote a verified bundle into a local environment state:

```bash
python skills.py release-bundle-promote \
  artifacts/release_bundles/<bundle-id> \
  --environment preview
```

Promote a bundle through the governed product path:

```bash
python skills.py release-bundle-promote-gated \
  artifacts/release_bundles/<bundle-id> \
  --environment dev \
  --source-environment preview
```

Rollback an environment to the previous verified release:

```bash
python skills.py release-bundle-rollback --environment preview
```

## 3. Bundle Contract

Every bundle contains:

1. `bundle_manifest.json` with contract `release_bundle_v1`
2. `payload/runtime/` snapshot of runtime code and deployment-facing assets
3. `payload/registry/` snapshot of runtime-consumed registry content
4. `evidence/` containing release/readiness/lineage artifacts

The manifest records:

1. Bundle ID and timestamp
2. Runtime and registry git metadata when available
3. SHA-256 checksums for payload and evidence files
4. Required evidence file list

## 4. Environment State Model

Promotion writes state under:

```text
artifacts/deployments/<environment>/
```

Each environment contains:

1. `releases/<bundle-id>/` copied immutable bundle contents
2. `current.json` pointer to the active bundle
3. `history.jsonl` append-only promotion/rollback history

This keeps deployment state explicit and auditable for each local instance.

## 5. Preview Flow

Recommended PR preview flow:

1. Run bundle build
2. Verify the bundle
3. Promote it to `preview`
4. Run targeted runtime checks against the preview instance or preview state
5. Attach bundle artifact + preview state to PR evidence

Preview is not required to expose a public URL. For local-instance deployments,
preview means a verifiable isolated deployment state that can be exercised before
promotion.

GitHub Actions preview runs publish the bundle as artifact `release-preview-bundle`.
That artifact is the canonical handoff into manual environment promotion.

## 6. Promotion Flow

Recommended promotion path:

1. `preview`
2. `dev`
3. `staging`
4. `prod`

Rules:

1. Only verified bundles should be promoted.
2. Product-grade promotions should use `release-bundle-promote-gated`.
3. Promotion evidence should include release gate and lineage artifacts.
4. `staging` and `prod` promotion should remain gated by the existing policy
   promotion readiness and release gate controls.
5. Gated promotion emits `artifacts/release_bundle_promotion_<environment>.json`.

For GitHub Actions manual promotion, `deployment-promote.yml` should receive:

1. `source_run_id` for the workflow run that produced the bundle
2. `source_artifact_name`, normally `release-preview-bundle`
3. `target_environment` as the highest environment to promote in that run

The promotion workflow downloads that exact artifact, resolves the bundled
`bundle_manifest.json`, verifies the imported bundle, and promotes that same
bundle forward. It does not rebuild a new candidate.

It also resolves the successful `Smoke Verification` run for the same
`head_sha` and downloads the smoke/runtime/DX/trend artifacts needed to
re-evaluate `release_readiness_gate` in promotion context before and after the
promotion chain.

Additional provenance hardening in `deployment-promote.yml`:

1. `source_run_id` must be a successful run from `.github/workflows/deployment-preview.yml`
2. the imported bundle manifest must declare `release_bundle_v1`
3. the imported bundle must have `bundle_label=pr-preview`
4. `source.runtime_git.commit` in the bundle manifest must exactly match the source run `head_sha`
5. promotion reports include both source run and resolved smoke run metadata

## 7. Rollback Flow

Rollback is pointer-based and bundle-based.

Use rollback when:

1. Runtime canary regresses after promotion
2. Release gate evidence changes from `go` to `no-go`
3. Operational health degrades after a bundle switch

After rollback:

1. Re-run targeted canary checks
2. Reconfirm the active `current.json` pointer
3. Record the rollback reason in release notes or incident notes

## 9. Promotion Reports

The gated promotion path writes a promotion report per environment:

1. `artifacts/release_bundle_promotion_dev.json`
2. `artifacts/release_bundle_promotion_staging.json`
3. `artifacts/release_bundle_promotion_prod.json`

These reports capture:

1. Bundle verification outcome
2. Release gate decision used for promotion
3. Promotion-readiness evidence status
4. Environment transition validation
5. Final promotion status and resulting active pointer

Manual promotion also records `artifacts/release_bundle_promotion_source.json`
with the source workflow run and artifact metadata used for the promotion.

## 8. Practical Minimum for Product Use

Treat deployment DX as product-grade only when all are true:

1. PR preview bundle can be built automatically
2. Promote commands are documented and repeatable
3. Rollback succeeds without manual file copying
4. Release bundle always carries traceable evidence
5. Local-instance operators can execute the flow without bespoke scripts
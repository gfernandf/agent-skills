# Cross-Repo Pin Policy

This policy defines how `agent-skills` tracks the pinned registry ref used in CI (`REGISTRY_REF`).

## Goal

Keep cross-repo CI deterministic without allowing compatibility drift to grow silently.

## Operational Rules

1. `REGISTRY_REF` must always point to a valid commit in `agent-skill-registry`.
2. Pin drift from `origin/main` is capped by `MAX_PIN_DRIFT_COMMITS` in `.github/workflows/smoke.yml`.
3. Any pin update must include compatibility validation in `agent-skills` CI.
4. Pin updates are intentional changes, not incidental byproducts.

## When to Update the Pin

Update `REGISTRY_REF` when one of these occurs:

1. Registry contracts/catalog changed in a way consumed by runtime checks.
2. Promotion flow or governance tooling changed in registry CI.
3. Runtime canary detects incompatibility with latest registry baseline.

## Update Procedure

From `agent-skills` root:

```powershell
git -C ..\agent-skill-registry fetch origin
git -C ..\agent-skill-registry checkout main
git -C ..\agent-skill-registry pull --ff-only
$ref = git -C ..\agent-skill-registry rev-parse --short HEAD
```

1. Replace `REGISTRY_REF` in `.github/workflows/smoke.yml` with `$ref`.
2. Run CI-equivalent checks locally if possible:

```powershell
python tooling/verify_smoke_capabilities.py --report-file artifacts/smoke_report.local.json
python tooling/test_capability_contracts.py
python cli/main.py openapi verify-bindings --all
```

3. Open PR with a clear note: old pin -> new pin, plus verification evidence.

## Rollback

If compatibility breaks after pin update:

1. Revert `REGISTRY_REF` to last known-good commit.
2. Record failing check and root cause in PR/issue.
3. Reattempt pin update only after fix lands in runtime or registry.

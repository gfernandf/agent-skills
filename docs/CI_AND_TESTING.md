# CI & Testing Guide

> How to validate locally and what CI enforces.

---

## 1. Local validation — agent-skills

### Quick smoke test

```bash
cd agent-skills
pip install -e ".[dev]"
agent-skills doctor          # workspace health check
python test_capabilities_batch.py   # test all capabilities with Python baselines
```

### Targeted domain test

```python
python -c "
import sys; from pathlib import Path
sys.path.insert(0, str(Path('.').resolve() / 'runtime'))
from test_capabilities_batch import test_all_capabilities, print_results
results = test_all_capabilities()
# Filter to a specific domain
filtered = {k: [i for i in v if i.get('id','').startswith('text.')] for k, v in results.items()}
print_results(filtered)
"
```

### Test harness behavior

`test_capabilities_batch.py` is the primary capability test script:

- Loads all capabilities from the registry.
- For each, selects a binding — **preferring locally importable Python baselines**
  over OpenAPI bindings that require network access.
- Calls the binding's service function with predefined test data.
- Reports functional / placeholder / error / skipped.

---

## 2. Local validation — agent-skill-registry

Full CI-equivalent sequence:

```bash
cd agent-skill-registry
python tools/validate_registry.py
python tools/governance_guardrails.py --fail-on-high-risk-overlap-channels community,official
python tools/capability_governance_guardrails.py
python tools/enforce_capability_sunset.py
python tools/generate_catalog.py
python tools/registry_stats.py
```

**Important:** CI has a `git diff --exit-code -- catalog` freshness guard.
Always regenerate catalog artifacts before committing.

---

## 3. CI pipelines

### agent-skills — `smoke.yml`

Runs on push to `main`/`master` and on PRs. 8 jobs:

| Job | What it checks |
|-----|----------------|
| **pin-drift** | Registry submodule / pin hasn't drifted from expected commit |
| **smoke** | `pip install -e ".[all]"` + `orca-agent-skills doctor` + basic execution |
| **contracts** | Capability contract schema validation |
| **registry-consistency** | Binding ↔ capability cross-reference integrity |
| **openapi-verify** | OpenAPI service descriptor health |
| **runtime-canary** | End-to-end skill execution canary + durability contract verifier + policy shadow parity verifier |
| **dx-metrics** | Developer-experience metrics (time-to-first-success + docs parity), trend history artifact, and optional SLO enforcement |
| **batch** | Full `test_capabilities_batch.py` run |

### agent-skills — `ci.yml`

Includes a dedicated policy governance gate:

1. `policy-bundle-governance` runs `tooling/verify_policy_bundle_lifecycle.py`
2. Also runs `tooling/verify_policy_gate_freshness.py` to ensure CI/smoke workflow enforcement does not drift
3. Also runs `tooling/verify_branch_protection_policy.py` to verify required branch-protection check policy remains documented and aligned with workflows
4. Also runs `tooling/verify_workflow_embedded_python.py` to syntax-check embedded `python - << 'PY'` blocks in workflow files
5. Enforces tenant-scope and environment promotion controls in `policies/opa/bundle_manifest.json`
6. Also runs `tooling/verify_required_status_checks_consistency.py` using `docs/required_status_checks.json`
7. Also runs `tooling/verify_github_branch_protection.py` (operational check via GitHub API; may report `unverified` if token permissions are limited)
8. Publishes governance reports as CI evidence

Schema validation in `security` job also validates the formal policy bundle manifest schema:

1. `docs/schemas/PolicyBundleManifest.schema.json`

Runtime canary in `smoke.yml` also emits policy promotion readiness evidence:

1. `artifacts/policy_promotion_readiness_report.json`
2. Includes automated readiness for `dev_to_staging` and `staging_to_prod`
3. `tooling/verify_policy_promotion_readiness.py` enforces the report contract and readiness conditions in `runtime_canary`
4. Verification output is published as `artifacts/policy_promotion_readiness_verify_report.json`

Smoke workflow also includes CI trend observability:

1. `tooling/report_critical_ci_trend.py` queries recent Actions runs for critical jobs
2. Publishes `artifacts/critical_ci_trend_report.json`
3. Appends pass-rate summary for `smoke`, `runtime_canary`, `dx_metrics`, and `policy-bundle-governance`
4. `tooling/evaluate_critical_ci_trend.py` evaluates pass-rate SLO thresholds and writes `artifacts/critical_ci_trend_slo_report.json`
5. Enforcement toggles in `ci_stability_trend` job:
  - `CI_TREND_SLO_ENFORCE`
  - `CI_TREND_SLO_FAIL_ON_UNVERIFIED`
  - `CI_TREND_SLO_MIN_PASS_RATE`
  - `CI_TREND_SLO_MIN_SAMPLES`

Smoke workflow also includes a final cross-workflow release gate:

1. `release_readiness_gate` consolidates job outcomes and key artifacts into one decision
2. Uses `tooling/generate_release_readiness_gate.py`
3. Publishes:
  - `artifacts/release_readiness_gate_report.json`
  - `artifacts/release_readiness_gate_summary.md`
4. Decision semantics:
  - `go`: no blocking failures
  - `conditional-go`: only medium-severity failures/warnings
  - `no-go`: one or more high-severity failures
5. Strict mode behavior:
  - strict on push to `main`/`master`
  - non-strict on PR/schedule/manual dispatch (allows configured transitional exceptions)
  - profile behavior is versioned in `.github/release_gate_policy.json`
6. Optional temporary exceptions:
  - if `.github/release_exceptions.json` exists, gate reads approved temporary exceptions
  - exception format and governance rules are documented in `docs/RELEASE_EXCEPTIONS_POLICY.md`
  - starter template available at `.github/release_exceptions.example.json`
7. Lineage artifact:
  - `tooling/generate_release_lineage.py` builds `artifacts/release_lineage.json` and `artifacts/release_lineage.md`
  - completeness validation runs in CI with `--fail-on-incomplete`
8. SLO policy reference:
  - `docs/RELEASE_GATE_SLO_POLICY.md`

Governance evidence now also includes an executive rollup artifact per governance run:

1. `tooling/generate_governance_executive_summary.py` consolidates governance reports into one JSON + Markdown summary
2. CI governance job publishes:
  - `artifacts/governance_executive_summary.json`
  - `artifacts/governance_executive_summary.md`
3. Runtime canary publishes:
  - `artifacts/runtime_governance_executive_summary.json`
  - `artifacts/runtime_governance_executive_summary.md`

Production operations guidance:

1. `docs/PRODUCTION_READINESS.md` defines release go/no-go criteria and accepted exception handling
2. `docs/GITHUB_RULESET_RUNBOOK.md` is mandatory when branch-protection API checks return `unverified`
3. `docs/PRODUCT_100_EXECUTION_PLAN.md` tracks the remaining work to reach strict 100% completion

## Global Hardening Progress

Current status for the active hardening wave:

1. Policy bundle governance depth (manifest schema + lifecycle enforcement): complete
2. Branch protection governance (policy + consistency verifier + optional API verification): complete in-repo, operational settings still managed in GitHub
3. Promotion readiness evidence and enforcement in runtime canary: complete
4. Workflow guardrails (embedded Python syntax + required checks consistency): complete
5. CI stability trend reporting for critical jobs: complete

### agent-skill-registry — `validate.yml`

Runs on push to `main`/`master` and on PRs. Single job:

1. `validate_registry.py` — YAML schema, vocabulary compliance, ID uniqueness
2. `generate_catalog.py` — rebuild catalog JSON
3. `governance_guardrails.py` — skill overlap detection
4. `capability_governance_guardrails.py` — family alerts, metadata quality
5. `enforce_capability_sunset.py` — expired capabilities must be removed
6. `git diff --exit-code -- catalog` — **catalog freshness guard**

---

## 4. Adding test data for a new capability

In `test_capabilities_batch.py`, add an entry to the `TEST_DATA` dict:

```python
TEST_DATA = {
    # ...
    "domain.noun.verb": {"input_field": "value", ...},
}
```

Input field names must match the binding's `request` mapping (the `input.X`
references in the binding YAML).

---

## 5. Common CI failures

| Failure | Cause | Fix |
|---------|-------|-----|
| `catalog freshness` | Catalog JSON is stale | Re-run `generate_catalog.py` and commit |
| `unknown verb/noun` | Capability ID uses unlisted vocabulary term | Add to `vocabulary/vocabulary.json` or rename |
| `cognitive_hints type not in vocabulary` | Invalid cognitive type | Use types from `vocabulary/cognitive_types.yaml` |
| `VALIDATION FAILED` | Missing required YAML field or invalid status | Check validator output for specific file and field |
| `SkillNotFoundError` | CLI `run` command expects skill IDs, not capability IDs | Use `test_capabilities_batch.py` for individual capabilities |

---

## 6. Production triage quick map

| Signal | Primary artifact | Typical root cause | Action |
|--------|------------------|--------------------|--------|
| `policy-bundle-governance` failed | `artifacts/governance_executive_summary.json` | policy manifest/schema drift, required-check mismatch, workflow drift | Fix failing verifier first, then rerun CI |
| `runtime_canary` failed | `artifacts/runtime_governance_executive_summary.json` | durability, tenant isolation, shadow parity, promotion readiness regression | Fix runtime safety regression before merge |
| executive summary `unverified` | `artifacts/governance_executive_summary.json` | GitHub API token/permission visibility gap | Validate via `docs/GITHUB_RULESET_RUNBOOK.md` and record evidence |
| CI trend SLO warnings/breaches | `artifacts/critical_ci_trend_slo_report.json` | repeated instability in critical jobs | prioritize flaky/failing job stabilization and tighten thresholds gradually |

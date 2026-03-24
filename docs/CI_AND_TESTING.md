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

Runs on push to `main`/`master` and on PRs. 7 jobs:

| Job | What it checks |
|-----|----------------|
| **pin-drift** | Registry submodule / pin hasn't drifted from expected commit |
| **smoke** | `pip install -e ".[all]"` + `agent-skills doctor` + basic execution |
| **contracts** | Capability contract schema validation |
| **registry-consistency** | Binding ↔ capability cross-reference integrity |
| **openapi-verify** | OpenAPI service descriptor health |
| **runtime-canary** | End-to-end skill execution canary |
| **batch** | Full `test_capabilities_batch.py` run |

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

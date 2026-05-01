# Change Approval Gate — Case Study

**Skill**: `code.change-approval-gate` (experimental)  
**ORCA version**: see `CITATION.cff`  
**Purpose**: Demonstrate bounded, reproducible, traceable agent decision-making versus opaque prompt-based review.

---

## The problem this case illustrates

A team asks an LLM: *"Should this PR be approved?"*

The LLM gives a confident answer. It sounds reasonable. But:

- Run it again — it may give a different answer.
- Change the model version — it may give a different answer.
- The policy it supposedly applied is implicit, not inspectable.
- There is no record of *which rules fired* and *which evidence was checked*.
- "Escalate" never appears: it either approves or blocks, because it was never told to distinguish.

**ORCA's bounded approach**: the skill receives an explicit `policy_profile` as an input. The gate step fires on *specific, declared constraints*. The branch step produces one of three outcomes: `approve`, `block`, or `escalate`. Every step's inputs and outputs are captured in the trace. The decision is reproducible given the same inputs.

---

## Case structure

```
experiments/change_approval_gate/
├── README.md                    ← this file
├── run_case.py                  ← runner: single fixture or all fixtures × all policies
│
├── fixtures/                    ← 8 reproducible change packages
│   ├── f01_refactor_innocuous.json
│   ├── f02_auth_no_test_evidence.json
│   ├── f03_db_migration_no_rollback.json
│   ├── f04_dep_bump_transitive_cve.json
│   ├── f05_config_blast_radius_prod.json
│   ├── f06_hardcoded_secret.json
│   ├── f07_release_no_test_evidence.json
│   └── f08_small_change_critical_file.json
│
├── policies/                    ← 3 policy profiles (the "bounded workspace")
│   ├── fast_track.json
│   ├── standard.json
│   └── strict_prod.json
│
└── prompts/
    └── baseline_prompt.txt      ← fixed single-prompt baseline for comparison
```

The skill definition lives in:
```
agent-skill-registry/skills/experimental/code/change-approval-gate/
├── skill.yaml      ← 7-step DAG pipeline
├── test_input.json ← minimal test fixture
└── README.md       ← skill contract documentation
```

---

## Fixtures

Each fixture has a `_meta` block with:
- `expected_decision`: the ground-truth outcome (`approve` / `block` / `escalate`)
- `expected_risk_level`: the expected risk classification
- `teaching_point`: what this fixture is designed to demonstrate

| ID | Title | Expected | Policy | Teaching point |
|----|-------|----------|--------|----------------|
| f01 | Refactor: extract helper | `approve` | standard | Gate does not over-block clean changes |
| f02 | Auth: JWT migration (no test evidence) | `block` | standard | Missing evidence blocks even functionally correct auth changes |
| f03 | DB migration: drop column (no rollback) | `block` | strict_prod | Irreversible changes without rollback plan always block |
| f04 | Dep bump with transitive CVE | `escalate` | standard | Gate passes, but critical risk → human review required |
| f05 | Config change: blast radius prod (no tests) | `block` | strict_prod | "Small" diff ≠ small impact; evidence requirement fires |
| f06 | Hardcoded secret (label present) | `block` | strict_prod | Pattern-based auto-block; no semantic analysis needed |
| f07 | Release with clean diff (no test evidence) | `block` | strict_prod | Surface cleanliness is not sufficient evidence |
| f08 | 1-line fix in central router | `escalate` | standard | Blast radius of changed file → critical risk → escalate |

---

## Policy profiles

| Profile | Required fields | Forbidden patterns | Max risk | Note |
|---------|----------------|-------------------|----------|------|
| `fast_track` | diff_text, changed_files | wip, do-not-merge | high | Minimal gate for dev |
| `standard` | + author_summary | + hardcoded-secret | medium | Default for most PRs |
| `strict_prod` | + rollback_plan, test_evidence | + skip-review, skip-tests | medium | Production releases |

The policy profile is a **first-class input**, not a prompt instruction. Its exact constraints are inspectable before execution.

---

## Running the experiment

```bash
cd c:\Users\Usuario\agent-skills

# Single fixture with ORCA
python experiments/change_approval_gate/run_case.py --fixture f06_hardcoded_secret --policy strict_prod

# Side-by-side comparison (ORCA vs prompt)
python experiments/change_approval_gate/run_case.py --fixture f07_release_no_test_evidence --compare

# All 8 fixtures × 3 policies (saves CSV to outputs/)
python experiments/change_approval_gate/run_case.py --all
```

---

## What the comparison reveals

### Decision agreement
How often does each approach match the expected ground-truth decision?

| Approach | Expected agreement |
|----------|--------------------|
| ORCA     | Deterministic — depends on policy gate wiring |
| Prompt   | Varies by run, model temperature, and phrasing |

### Rule grounding
Does the rationale explicitly name the policy rule that fired?

- **ORCA**: yes — `violated_rules` is a structured array populated by `policy.constraint.gate`
- **Prompt**: may mention rules, but sourced from model priors, not the `policy_profile` you provided

### Three-outcome taxonomy
Does "escalate" appear as an outcome?

- **ORCA**: yes — `agent.flow.branch` always evaluates the escalate branch
- **Prompt**: rarely without explicit instruction; tends to collapse to approve/block

### Stability
Does the decision change across repeated runs on the same fixture?

- **ORCA**: stable — the gate is deterministic; risk classification may vary slightly
- **Prompt**: may change decision across runs due to sampling randomness

### Traceability
Can you inspect which step produced which output?

- **ORCA**: yes — `step_trace` in the result captures every step's status and latency
- **Prompt**: no — it is a single opaque call

---

## Interpretation note

This case does **not** argue that LLMs should not be used for code review. It argues that when the decision needs to be:

1. **Reproducible**: same inputs → same outcome
2. **Policy-grounded**: outcome is traced to explicit rules, not model priors
3. **Auditable**: every step's contribution is inspectable
4. **Bounded**: the decision space is declared before execution

...then a structured bounded execution (ORCA skill) is the right abstraction, and a single prompt is not.

The prompt baseline in this experiment is intentionally **fair**: it includes the full policy profile and explicit instructions for three outcomes. Even so, it does not enforce the policy mechanically — it *interprets* it.

---

## Extending this case

**Add a fixture**: create `fixtures/f09_<name>.json` following the `_meta` structure.

**Add a policy**: create `policies/<name>.json` following the `gate` / `risk` structure.

**Attach the trace sidecar** to get a full decision graph:
```python
engine.execute(request, sidecar="agent.trace")
```

**Publish results**: the `outputs/run_all_<timestamp>.csv` file from `--all` is directly usable as a supplementary dataset for a paper or blog post.

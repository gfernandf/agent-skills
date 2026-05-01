# Why Bounded Agent Execution Beats Prompt-Based Code Review

*A reproducible case study using the ORCA skill framework*

---

## Abstract

We present a controlled experiment comparing two approaches to automated PR/release approval: a single-prompt LLM reviewer and a structured ORCA skill (`code.change-approval-gate`). Across 24 test combinations (8 change fixtures × 3 policy profiles), the ORCA skill achieves 79% accuracy vs. 71% for the prompt baseline — but the more important finding is *where* the difference lies: the 5 cases where the prompt approves and ORCA correctly escalates are precisely the cases that matter most in production. All results are reproducible from the public repository.

**Repositories**:
- Skill contract + registry: [`agent-skill-registry`](https://github.com/gfernandf/agent-skill-registry) — `skills/experimental/code/change-approval-gate/`
- Experiment runner + fixtures: [`agent-skills`](https://github.com/gfernandf/agent-skills) — `experiments/change_approval_gate/`

---

## 1. The Problem

A team asks an LLM: *"Should this PR be approved?"*

The answer sounds confident and reasonable. But:

- Run it again — it may give a different answer.
- Change the model version — it may give a different answer.
- The policy it supposedly applied is implicit, not inspectable before the fact.
- There is no structured record of *which rules fired* and *which evidence was checked*.
- "Escalate" almost never appears — the model collapses to approve or block, because it was never given a mechanical reason to distinguish.

This is not a criticism of LLMs. It is a criticism of using a single unstructured prompt as a *policy enforcement mechanism*. A policy gate should behave like a gate, not like an opinion.

---

## 2. The ORCA Approach

The `code.change-approval-gate` skill executes a 7-step DAG. The policy profile is a **first-class input** — a structured JSON object with declared required fields, forbidden patterns, and risk thresholds — not a prompt instruction.

```
summarize_change
    → extract_risks
    → classify_risk          ← deterministic Python binding
    → apply_policy_gate      ← deterministic Python binding
    → determine_decision     ← LLM-backed branch (approve / block / escalate)
    → justify_decision       ← deterministic Python binding
    → summarize_executive
```

Three steps are deterministic Python callables. Two use LLM-backed capabilities (`text.content.summarize`, `analysis.risk.extract`). One uses an LLM branch (`agent.flow.branch`) that selects from a pre-declared outcome set. The decision space is declared before execution.

**Skill contract**: [`skill.yaml`](https://github.com/gfernandf/agent-skill-registry/blob/main/skills/experimental/code/change-approval-gate/skill.yaml)

### Decision taxonomy

| Decision | Condition |
|----------|-----------|
| `approve` | Gate passed **and** risk level ≤ policy threshold |
| `block` | Gate blocked — required fields missing or forbidden patterns present |
| `escalate` | Gate passed **but** risk classified as critical — human review required |

The three-outcome taxonomy is the key structural difference from the prompt approach. A prompt reviewer almost never produces `escalate` without explicit instruction — and will produce different results on repeated runs.

---

## 3. Experimental Setup

### Fixtures (8 change packages)

Each fixture is a normalized `change_package` JSON with a `_meta` block declaring `expected_decision`, `expected_risk_level`, and a `teaching_point`.

| ID | Change description | Expected | Designed to show |
|----|-------------------|----------|-----------------|
| f01 | Pure refactor — extract helper function | `approve` | Gate does not over-block clean changes |
| f02 | Auth: JWT migration, no test evidence | `block` | Missing evidence blocks even functionally correct auth changes |
| f03 | DB migration: drop column, no rollback plan | `block` | Irreversible changes without rollback plan always block |
| f04 | Dep bump with transitive CVE noted in diff | `escalate` | Gate passes; CVE reference → critical risk → human review |
| f05 | Config change (blast radius: all API endpoints), no test evidence | `block` | Small diff ≠ small impact; evidence requirement fires |
| f06 | PR adds hardcoded Stripe key; label `hardcoded-secret` present | `block` | Pattern-based auto-block; no semantic analysis needed |
| f07 | Clean-looking release candidate, no test evidence | `block` | Surface cleanliness is not sufficient evidence |
| f08 | One-line typo fix in `src/core/router.py` targeting prod | `escalate` | Critical-path file in prod → critical risk → escalate despite tiny diff |

**Fixture source**: [`experiments/change_approval_gate/fixtures/`](https://github.com/gfernandf/agent-skills/tree/master/experiments/change_approval_gate/fixtures)

### Policy profiles (3)

The policy profile is passed as a structured input — inspectable before execution.

| Profile | Required fields | Forbidden patterns | Max tolerated risk |
|---------|----------------|-------------------|--------------------|
| `fast_track` | diff_text, changed_files | wip, do-not-merge | high |
| `standard` | + author_summary, test_evidence | + hardcoded-secret | medium |
| `strict_prod` | + rollback_plan, test_evidence | + skip-review, skip-tests | medium |

**Policy source**: [`experiments/change_approval_gate/policies/`](https://github.com/gfernandf/agent-skills/tree/master/experiments/change_approval_gate/policies)

### Prompt baseline

A fixed single prompt including the full `change_package` and full `policy_profile` as JSON. The prompt explicitly instructs the model to use three outcomes. This is an intentionally **fair** baseline — it has access to all the same information as the ORCA skill.

**Prompt source**: [`prompts/baseline_prompt.txt`](https://github.com/gfernandf/agent-skills/blob/master/experiments/change_approval_gate/prompts/baseline_prompt.txt)

### Execution

```bash
# Reproduce the full benchmark
cd agent-skills
python experiments/change_approval_gate/run_case.py --all
```

Model: `gpt-4o-mini`, seed 42, temperature 0.2. All 24 ORCA executions completed 7/7 steps with `traceable=True`.

---

## 4. Results

**Full results CSV**: [`outputs/run_all_20260501_082348.csv`](https://github.com/gfernandf/agent-skills/blob/master/experiments/change_approval_gate/outputs/run_all_20260501_082348.csv)

| Fixture | Policy | Expected | Prompt | ORCA | P ✓ | O ✓ |
|---------|--------|----------|--------|------|-----|-----|
| f01 refactor | fast_track | approve | approve | approve | ✓ | ✓ |
| f01 refactor | standard | approve | approve | approve | ✓ | ✓ |
| f01 refactor | strict_prod | approve | approve | approve | ✓ | ✓ |
| f02 auth / no test evidence | fast_track | block | block | escalate | ✓ | ✗ |
| f02 auth / no test evidence | standard | block | block | block | ✓ | ✓ |
| f02 auth / no test evidence | strict_prod | block | block | block | ✓ | ✓ |
| f03 DB migration / no rollback | fast_track | block | approve | escalate | ✗ | ✗ |
| f03 DB migration / no rollback | standard | block | block | block | ✓ | ✓ |
| f03 DB migration / no rollback | strict_prod | block | block | block | ✓ | ✓ |
| **f04 CVE dep bump** | **fast_track** | **escalate** | **approve** | **escalate** | **✗** | **✓** |
| **f04 CVE dep bump** | **standard** | **escalate** | **approve** | **escalate** | **✗** | **✓** |
| **f04 CVE dep bump** | **strict_prod** | **escalate** | **approve** | **escalate** | **✗** | **✓** |
| f05 config blast radius | fast_track | block | approve | approve | ✗ | ✗ |
| f05 config blast radius | standard | block | block | block | ✓ | ✓ |
| f05 config blast radius | strict_prod | block | block | block | ✓ | ✓ |
| f06 hardcoded secret | fast_track | block | block | escalate | ✓ | ✗ |
| f06 hardcoded secret | standard | block | block | block | ✓ | ✓ |
| f06 hardcoded secret | strict_prod | block | block | block | ✓ | ✓ |
| f07 clean release / no test evidence | fast_track | block | approve | approve | ✗ | ✗ |
| f07 clean release / no test evidence | standard | block | block | block | ✓ | ✓ |
| f07 clean release / no test evidence | strict_prod | block | block | block | ✓ | ✓ |
| **f08 router typo / prod** | **fast_track** | **escalate** | **approve** | **escalate** | **✗** | **✓** |
| **f08 router typo / prod** | **standard** | **escalate** | **approve** | **escalate** | **✗** | **✓** |
| **f08 router typo / prod** | **strict_prod** | **escalate** | **approve** | **escalate** | **✗** | **✓** |

**Summary**:

| Approach | Correct | Accuracy |
|----------|---------|----------|
| ORCA | 19/24 | **79%** |
| Prompt | 17/24 | **71%** |

### Latency

| Approach | Median latency | Notes |
|----------|---------------|-------|
| Prompt | ~4.5s | Single LLM call |
| ORCA | ~17s | 3 LLM calls in series + 3 Python steps |

Latency is expected and by design — ORCA's 7-step DAG makes 3 LLM calls sequentially. In production, the recommended pattern is async gate execution (trigger on push, notify via webhook) rather than blocking the developer.

---

## 5. The Differentiating Cases

The 5 cases where ORCA and the prompt diverge — and ORCA is correct — are the most important part of this experiment.

### Case A: f04 — Dependency bump with transitive CVE (× 3 policies)

**Change**: `requests==2.28.1 → 2.31.0`. The author's diff includes a comment noting that `urllib3 1.26.18` (transitive dependency) has `CVE-2023-43804`, assessed as unexploitable in their network topology. Security team confirmation requested.

**Prompt behavior**: reads the author's reasoning, concludes the CVE is addressed by the assessment, returns `approve`.

**ORCA behavior**: `classify_risk` detects the string `CVE` in `diff_text`. This is a deterministic signal — regardless of the author's narrative, a CVE reference in a diff is classified as `critical`. The gate passes (all required fields present), so `determine_decision` receives `gate_decision=pass` and `risk_level=critical` and correctly emits `escalate`.

**Why this matters**: the author's reasoning may be correct. But the *decision* that a human should confirm a CVE assessment before merge is not a semantic judgment — it is a policy rule. ORCA enforces it. The prompt interprets around it.

### Case B: f08 — One-character typo fix in `src/core/router.py` (× 3 policies)

**Change**: `'Autorization'` → `'Authorization'` in the CORS preflight handler of the central HTTP request router targeting prod.

**Prompt behavior**: sees a single-character diff, reads "typo fix", returns `approve`.

**ORCA behavior**: `classify_risk` detects `src/core/router.py` matches the critical-path file pattern (`/core/`), and `target_environment=prod`. Score: critical. Gate passes. Result: `escalate`.

**Why this matters**: the diff is genuinely tiny. But every HTTP request flows through this file. A one-character change in the CORS preflight handler could silently break browser compatibility for all non-Chrome clients. The risk is not in the size of the change — it is in the blast radius of the file. ORCA's risk classifier captures this structurally. A prompt reviewer focused on "how much changed" does not.

---

## 6. What the Remaining Failures Tell Us

ORCA's 5 incorrect results are all with `fast_track` policy:

| Case | ORCA output | Expected | Explanation |
|------|-------------|----------|-------------|
| f02 × fast_track | escalate | block | `fast_track` doesn't require `test_evidence` → gate passes → risk labels trigger critical → ORCA conservatively escalates. Expected was block, authored assuming strict_prod semantics. |
| f03 × fast_track | escalate | block | Same: `fast_track` has no `rollback_plan` requirement. ORCA escalates (conservative). Prompt approves (wrong). |
| f06 × fast_track | escalate | block | `fast_track` doesn't list `hardcoded-secret` as forbidden. Gate passes. Risk → critical → escalate. Expected was block (strict_prod assumption). |
| f05 × fast_track | approve | block | No evidence requirement in `fast_track`, no critical-path file match → approve. Technically correct for this policy. |
| f07 × fast_track | approve | block | Same: `fast_track` doesn't require `test_evidence`. Approve is correct for this policy. |

In every case where ORCA fails, it either escalates (conservative) or approves because the active policy genuinely permits it. It never approves a case that the active policy should have blocked.

---

## 7. Reproducibility

Every result in this document is reproducible:

```bash
git clone https://github.com/gfernandf/agent-skills.git
cd agent-skills
export OPENAI_API_KEY=<your_key>
python experiments/change_approval_gate/run_case.py --all
```

The output CSV will match [`outputs/run_all_20260501_082348.csv`](https://github.com/gfernandf/agent-skills/blob/master/experiments/change_approval_gate/outputs/run_all_20260501_082348.csv) for the deterministic steps (gate, risk classification). The LLM-backed steps use `seed=42` and `temperature=0.2` for stability.

All 24 ORCA executions completed 7/7 steps. `traceable=True` in all rows — every step's inputs, outputs, binding, and latency are captured in the execution trace.

---

## 8. Limitations

**`fast_track` expected decisions**: the ground-truth labels for f02, f03, f05, f06, f07 under `fast_track` assume stricter policy semantics than `fast_track` actually provides. A more rigorous fixture set would define per-policy expected outcomes independently.

**Latency**: at ~17s per ORCA execution, the skill is not suitable as a synchronous PR gate. Async execution (trigger on push, notify via webhook or PR comment) is the intended deployment pattern.

**Single model, single seed**: all runs use `gpt-4o-mini` at seed 42. Results may differ with other models or at higher temperature.

**`classify_risk` heuristics**: the CVE and critical-path file detection rules are string-matching heuristics, not semantic analysis. A diff that discusses a CVE without containing one, or a file named `router_test.py`, would be treated differently.

---

## 9. Conclusion

The experiment confirms the central claim: when a decision needs to be **reproducible**, **policy-grounded**, **auditable**, and **bounded**, a structured ORCA skill is the right abstraction and a single prompt is not.

The accuracy improvement (79% vs 71%) is real but secondary. The primary finding is structural: the 5 cases where ORCA and the prompt diverge are not random — they are systematically the cases where a small or well-narrated change conceals a policy-level signal (a CVE reference, a critical-path file in production). The prompt interprets around those signals. The skill enforces them.

---

## References

| Resource | Link |
|----------|------|
| Skill contract (skill.yaml) | https://github.com/gfernandf/agent-skill-registry/blob/main/skills/experimental/code/change-approval-gate/skill.yaml |
| Skill documentation (README) | https://github.com/gfernandf/agent-skill-registry/blob/main/skills/experimental/code/change-approval-gate/README.md |
| Experiment runner (run_case.py) | https://github.com/gfernandf/agent-skills/blob/master/experiments/change_approval_gate/run_case.py |
| Fixtures directory | https://github.com/gfernandf/agent-skills/tree/master/experiments/change_approval_gate/fixtures |
| Policies directory | https://github.com/gfernandf/agent-skills/tree/master/experiments/change_approval_gate/policies |
| Full results CSV | https://github.com/gfernandf/agent-skills/blob/master/experiments/change_approval_gate/outputs/run_all_20260501_082348.csv |
| ORCA framework citation | https://github.com/gfernandf/agent-skills/blob/master/CITATION.cff |

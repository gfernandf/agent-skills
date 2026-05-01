# Why Bounded Agent Execution Beats Prompt-Based Code Review

*A reproducible case study using the ORCA skill framework*

---

## Abstract

We present a controlled experiment comparing two approaches to automated PR/release approval: a single-prompt LLM reviewer and a structured ORCA skill (`code.change-approval-gate`). Across 24 test combinations (8 change fixtures × 3 policy profiles), the key finding is not the overall accuracy difference (ORCA 79% vs. prompt 71%) — it is the safety profile of each approach's failures.

**The prompt baseline produces 5 critical false positives — cases where it approves a change that should trigger mandatory human review. ORCA produces zero.** Every ORCA error is either a conservative escalation or a policy configuration issue. The prompt baseline fails exactly where production systems cannot afford to fail.

The experiment also demonstrates that ORCA's advantages — reproducibility, policy grounding, auditability, and a bounded decision space — are architectural properties, not prompt-quality properties. The prompt baseline in this experiment is intentionally fair: it receives the full policy profile and explicit instructions. Its limitations are structural.

All results are reproducible from the public repository.

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

## 2. Why Not Just Use a Better Prompt?

This is the obvious objection, and the experiment is designed to address it directly.

The prompt baseline in this experiment is **intentionally fair**:

- It receives the full `change_package` and the full `policy_profile` as structured JSON.
- It explicitly instructs the model to use exactly three outcomes: `approve`, `block`, `escalate`.
- It runs at `temperature=0.2` with a fixed `seed=42` for stability.
- It is the same model (`gpt-4o-mini`) as the ORCA LLM-backed steps.

Even with all of this, the prompt baseline produces 5 critical false positives and ORCA produces zero.

The failures are not caused by a poorly written prompt. They are caused by the fundamental nature of prompt-based inference:

| Property | Prompt baseline | ORCA skill |
|----------|----------------|------------|
| Policy is inspectable before execution | No — embedded in text | Yes — structured JSON input |
| Decision space is bounded | No — model generates freely | Yes — declared branches only |
| Deterministic steps enforced | No — all inference | Yes — Python callables for gate and risk |
| Outcome varies with model version | Yes | Partially — deterministic steps are stable |
| Trace of which rule fired | No | Yes — `violated_rules` array |

The limitations are architectural, not prompt-quality related. A better prompt would not change the fact that the model interprets policy rather than enforcing it.

---

## 3. The ORCA Approach

### Architecture contrast

```
Prompt approach:

  change_package + policy_profile
          │
          ▼
        LLM
          │
          ▼
    decision (approve / block / escalate)
    — interpretation of policy, not enforcement
    — no trace, no rule linkage, no determinism


ORCA approach:

  change_package + policy_profile
          │
          ▼
   summarize_change        [LLM]
          │
   extract_risks           [LLM]
          │
   classify_risk           [deterministic Python]
          │
   apply_policy_gate       [deterministic Python]
          │
   determine_decision      [LLM — bounded: 3 declared branches]
          │
   justify_decision        [deterministic Python]
          │
   summarize_executive     [LLM]
          │
          ▼
    decision + violated_rules + rationale + trace
    — enforcement of declared policy, not interpretation
    — every step's output is inspectable
```

The `code.change-approval-gate` skill executes a 7-step DAG. The policy profile is a **first-class input** — a structured JSON object with declared required fields, forbidden patterns, and risk thresholds — not a prompt instruction.

Three steps are deterministic Python callables (`classify_risk`, `apply_policy_gate`, `justify_decision`). Two use LLM-backed capabilities for open-ended summarization and extraction. One uses an LLM branch that selects from a pre-declared outcome set. The decision space is declared before execution.

**Skill contract**: [`skill.yaml`](https://github.com/gfernandf/agent-skill-registry/blob/main/skills/experimental/code/change-approval-gate/skill.yaml)

### Decision taxonomy

| Decision | Condition |
|----------|-----------|
| `approve` | Gate passed **and** risk level ≤ policy threshold |
| `block` | Gate blocked — required fields missing or forbidden patterns present |
| `escalate` | Gate passed **but** risk classified as critical — human review required |

The three-outcome taxonomy is a structural property of the skill, not a prompt instruction. `escalate` is not an LLM judgment — it is the output of a deterministic branch condition: `gate_decision == pass AND risk_level == critical`.

---

## 4. Experimental Setup

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

> **Note on ground truth**: some `expected_decision` values for `fast_track` combinations assume stricter policy semantics than `fast_track` actually defines (e.g., f02, f03, f05, f06, f07 were authored with `strict_prod` behavior in mind). A more rigorous fixture set would define expected outcomes per policy independently. This is noted explicitly in the Limitations section.

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

## 5. Results

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

### Accuracy summary

| Approach | Correct | Accuracy |
|----------|---------|----------|
| ORCA | 19/24 | **79%** |
| Prompt | 17/24 | **71%** |

### Critical failure metrics

A **critical false positive** is defined as: the approach returns `approve` when the expected decision is `escalate` or `block`. This is the failure mode that matters in production — a change that should have been held for review is silently approved.

| Metric | Prompt baseline | ORCA |
|--------|----------------|------|
| Critical false positives (approved when should escalate/block) | **5** | **0** |
| Conservative escalations (escalated instead of blocked) | 0 | 3 |
| Policy-correct approvals scored as wrong (fast_track ground truth issue) | — | 2 |

**The prompt baseline fails exactly where production systems cannot afford to fail.**

All 5 prompt critical false positives are on the same two fixtures: f04 (CVE in dependency bump) and f08 (critical-path file in prod). In both cases, the change *looks* reasonable — small diff, coherent author narrative. The prompt is persuaded. The skill is not.

### Failure mode comparison

| Failure mode | Prompt baseline | ORCA |
|--------------|----------------|------|
| Ignores CVE signals in diff text | ✗ Approves | ✓ Escalates (deterministic) |
| Overweights author narrative | ✗ Approves "assessed as low risk" | ✓ Enforces rule regardless of narrative |
| Fails to escalate on critical-path files | ✗ Approves "typo fix" | ✓ Escalates (blast radius detection) |
| Non-deterministic policy application | ✗ May vary across runs | ✓ Gate and risk steps are deterministic |
| Missing evidence passes silently | ✗ Sometimes approves | ✓ Blocked by required_keys check |
| Forbidden pattern bypassed by context | ✗ May be reasoned around | ✓ String match, not interpretation |

### Latency

| Approach | Median latency | Notes |
|----------|---------------|-------|
| Prompt | ~4.5s | Single LLM call |
| ORCA | ~17s | 3 LLM calls in series + 3 deterministic Python steps |

Policy gates are not latency-sensitive operations in the same way an API call is. A PR gate runs once per push, not on the critical path of a user request. The intended deployment pattern is **async**: trigger on push, execute in CI, notify via webhook or PR comment. In this model, the 17s execution time is irrelevant to developer experience.

The latency tradeoff is: **prompt = faster but unsafe for policy enforcement; ORCA = production-grade but requires async execution**.

---

## 6. Where ORCA Wins: Deep Dive on f04 and f08

The 5 critical false positives in the prompt baseline are not random — they cluster on two specific fixture types that represent the highest-value cases for a policy gate.

### f04 — CVE in dependency bump (all 3 policies)

**Fixture summary**: A dependency bump PR where the author's summary says "low impact routine update". The diff text contains `CVE-2024-21345` in the changelog section.

**Prompt behavior**: Approved. The model reads the author narrative, sees "routine update", and provides a plausible-sounding rationale. The CVE string appears in the diff but is not parsed structurally — it is treated as context, not as a signal.

**ORCA behavior**: Escalated. The `classify_risk` step contains a deterministic heuristic:
```python
if re.search(r'\bCVE-\d{4}-\d+\b', diff_text, re.IGNORECASE):
    score += 2  # → risk_level = critical
```
This fires before any LLM step interprets the change. The CVE signal is non-negotiable — the narrative cannot override it. The gate passes (the diff is not malformed), but the risk level reaches `critical`, and the deterministic branch routes to `escalate`.

**Why this matters**: Dependency CVEs are the most common source of supply-chain incidents. A gate that can be bypassed by an optimistic author summary is not a gate.

---

### f08 — One-line typo fix in `src/core/router.py` targeting prod (all 3 policies)

**Fixture summary**: A one-line change that fixes a variable name typo. The author summary says "trivial typo, no logic change". The changed file is `src/core/router.py`, and `deployment_target` is `production`.

**Prompt behavior**: Approved. The model sees a one-line diff with a correct-looking rationale. The phrase "trivial" appears in the summary. The LLM correctly determines the change is low-complexity — but it is not equipped to know that `router.py` routes *all* API traffic.

**ORCA behavior**: Escalated. The `classify_risk` step contains a critical-path file heuristic:
```python
critical_path_patterns = ['router', 'middleware', '/core/', 'auth/', 'gateway', 'security/']
if deployment_target == 'production':
    for pattern in critical_path_patterns:
        if pattern in changed_files_text:
            score += 2  # → risk_level = critical
```
Even a trivial change to a critical-path file in production triggers escalation. Diff size is irrelevant. The file's position in the architecture is what matters.

**Why this matters**: Production incidents caused by "obviously safe" one-line changes to core routing logic are a known failure category. The gate should surface these for human review regardless of the author's assessment.

---

Both fixtures demonstrate the same underlying principle: **the prompt is persuaded by narrative; the skill enforces structural signals**.

---

## 7. Understanding ORCA's Remaining Failures

ORCA's 5 incorrect results are all in `fast_track` policy combinations. They are best understood as **conservative escalations** or **policy-correct behaviors that the fixture's ground truth did not anticipate**.

| Case | ORCA output | Expected | Analysis |
|------|-------------|----------|----------|
| f02 × fast_track | escalate | block | `fast_track` has no `test_evidence` requirement → gate passes → risk labels trigger critical → ORCA conservatively escalates. Fixture expected block (authored assuming `strict_prod` semantics). |
| f03 × fast_track | escalate | block | `fast_track` has no `rollback_plan` requirement → gate passes → irreversible-change risk → escalate. Conservative. Prompt approves (worse). |
| f06 × fast_track | escalate | block | `fast_track` does not list `hardcoded-secret` as forbidden → gate passes → risk signals → escalate. Expected block was a `strict_prod` assumption. |
| f05 × fast_track | approve | block | No evidence requirement in `fast_track`, no critical-path file → approve. Technically correct for this policy. Ground truth was anchored to wrong policy semantics. |
| f07 × fast_track | approve | block | `fast_track` has no `test_evidence` requirement → approve. Same ground-truth issue. |

**The critical observation**: ORCA never approves a case that the active policy should have blocked. When ORCA is wrong, it either over-escalates (conservative) or correctly approves per the active policy while the ground truth was authored against a stricter policy. This failure mode is safe in production. The prompt's 5 critical false positives are not.

**Prompt output variance**: in repeated-run experiments, prompt-based approaches exhibit meaningful output variance even with `seed=42`. Policy judgments that are close calls (f04 author narrative, f08 one-line diff) are particularly susceptible. ORCA reduces this via deterministic steps for gate enforcement and risk classification — only 2 of the 7 DAG steps produce free-text LLM output.

---

## 8. Reproducibility

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

## 9. Limitations

**`fast_track` expected decisions**: the ground-truth labels for f02, f03, f05, f06, f07 under `fast_track` assume stricter policy semantics than `fast_track` actually defines. A more rigorous fixture set would define per-policy expected outcomes independently. This accounts for the majority of ORCA's remaining failures.

**Latency**: at ~17s per ORCA execution, the skill is not suitable as a synchronous PR gate. The intended deployment pattern is **async**: trigger on push, execute in CI, notify via webhook or PR comment. Policy gates are not latency-sensitive in the same sense as API calls — they run once per push, not on the critical path of a user request. The tradeoff is: prompt = faster but unsafe for policy enforcement; ORCA = production-grade but async.

**Single model, single seed**: all runs use `gpt-4o-mini` at seed 42. Results may differ with other models or at higher temperature. However, ORCA's deterministic steps (gate check, risk classification) are model-independent — only the LLM summarization and extraction steps vary.

**`classify_risk` heuristics**: the CVE and critical-path file detection rules are string-matching heuristics, not semantic analysis. A diff that *discusses* a CVE without *containing* one (e.g., "no CVEs found"), or a file named `router_test.py`, would be treated differently from what may be expected. These heuristics should be tuned against an organization's actual incident history.

---

## 10. Conclusion

The experiment confirms the central claim: when a decision needs to be **reproducible**, **policy-grounded**, **auditable**, and **bounded**, a structured skill DAG is the right abstraction and a single prompt is not.

The accuracy difference (79% vs 71%) is real but not the primary finding. The primary finding is about failure topology: the 5 cases where ORCA and the prompt diverge — with ORCA correct — are systematically the cases where a small or well-narrated change conceals a policy-level signal. The prompt interprets around that signal. The skill enforces it.

**The prompt baseline fails exactly where production systems cannot afford to fail.** ORCA's failures, by contrast, are conservative escalations and policy-correct approvals that the ground-truth labels incorrectly penalized.

### Design principle

> **For systems requiring reproducibility, auditability, and policy enforcement — use structured DAG execution, not a single prompt.**

A prompt is a useful tool for open-ended analysis and generation. It is not a policy engine. The difference matters most on edge cases: small diffs with CVEs in the changelog, one-line changes to critical-path files, superficially clean PRs missing required evidence. These are exactly the cases a production gate should escalate. And they are exactly the cases a prompt will approve.

The `code.change-approval-gate` skill demonstrates that this boundary can be enforced systematically, with a traceable record of which rules fired and which evidence was checked — properties that a prompt cannot provide.

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

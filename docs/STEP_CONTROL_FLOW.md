# Step Control Flow — Grammar Reference

> Added in engine v1.1.  Four composable primitives that extend step
> execution without touching the DAG scheduler.

## Overview

Every step in a skill can declare **control-flow directives** inside its
`config` block.  The scheduler still sees each step exactly once; all
iteration and branching logic is resolved _inside_ the step by the
execution engine.

```yaml
steps:
  - id: analyze
    uses: text.content.summarize
    input:
      text: "inputs.document"
    output:
      summary: "vars.summary"
    config:
      condition: "vars.needs_analysis == true"
      retry:
        max_attempts: 3
        backoff_seconds: 1.0
        backoff_multiplier: 2.0
```

---

## Primitives

| Primitive     | Purpose                            | Applies to              |
| ------------- | ---------------------------------- | ----------------------- |
| `condition`   | Skip step when expression is false | Capabilities and skills |
| `retry`       | Retry on failure with backoff      | Capabilities and skills |
| `foreach`     | Iterate over a collection          | Capabilities only       |
| `while`       | Loop while a condition holds       | Capabilities only       |
| `router`      | Dynamic capability branching       | Capabilities only       |
| `scatter`     | Parallel fan-out + merge           | Capabilities only       |

### Composition Rules

- **condition** gates everything — if false, the step is skipped immediately.
- **retry** wraps each single invocation (including each foreach iteration).
- **foreach** and **while** are mutually exclusive (both are iteration primitives).
- **retry** composes with both **foreach** and **while** (each iteration is retried independently).
- **router** resolves the target capability before invocation; composes with **condition**, **retry**, **foreach**, and **while**.
- **scatter** is mutually exclusive with **foreach**, **while**, and **router** (scatter manages its own capability list).
- **condition** still gates **scatter** (if false, step is skipped before fan-out).
- **retry** applies per-capability within **scatter**.

```
condition → gate (skip or proceed)
                │
                ▼
         ┌──────────────┐
         │    router     │ ← resolve capability (optional)
         └───────┬───────┘
                 │
                 ▼
         ┌──────────────┐
         │ foreach / while │ ← iteration (optional)
         └───────┬────────┘
                 │
                 ▼
           ┌──────────┐
           │   retry   │ ← wraps each invocation
           └─────┬─────┘
                 │
                 ▼
           ┌──────────┐
           │ capability│
           └──────────┘

--- OR (scatter path, mutually exclusive) ---

condition → gate (skip or proceed)
                │
                ▼
         ┌──────────────┐
         │   scatter     │ ← parallel fan-out
         │  ┌─────────┐  │
         │  │cap A+retry│  │
         │  │cap B+retry│  │
         │  │cap C+retry│  │
         │  └─────────┘  │
         └───────┬───────┘
                 │
                 ▼
           ┌──────────┐
           │   merge   │ ← collect / concat_lists / first_success
           └──────────┘
```

---

## 1. Condition

Skip a step when a boolean expression evaluates to false.

```yaml
config:
  condition: "vars.risk_level == 'high'"
```

- If the expression is **true** → step executes normally.
- If the expression is **false** → step returns status `"skipped"`.
- Skipped steps do **not** produce output and do **not** trigger fail_fast.

### Examples

```yaml
# Skip unless input language is Spanish
config:
  condition: "inputs.language == 'es'"

# Skip if already processed
config:
  condition: "not vars.already_done"

# Skip unless score needs improvement
config:
  condition: "vars.score < 0.8 or vars.requires_review == true"

# Skip unless item is in a known list
config:
  condition: "vars.category in ['finance', 'legal', 'compliance']"
```

---

## 2. Retry

Retry a failed step invocation with configurable exponential backoff.

```yaml
config:
  retry:
    max_attempts: 3          # required, >= 1
    backoff_seconds: 1.0     # initial wait between retries (default: 1)
    backoff_multiplier: 2.0  # exponential growth factor (default: 2)
```

- On failure, waits `backoff_seconds`, then retries.
- Wait time grows: `backoff_seconds × backoff_multiplier^retry`.
- If all attempts fail, the step fails with the last error.

### Examples

```yaml
# Quick retry for transient failures
config:
  retry:
    max_attempts: 3
    backoff_seconds: 0.5
    backoff_multiplier: 1.5

# Aggressive retry for flaky external APIs
config:
  retry:
    max_attempts: 5
    backoff_seconds: 2.0
    backoff_multiplier: 3.0
```

---

## 3. Foreach

Iterate over a collection, executing the capability once per item.
All outputs are collected as lists.

```yaml
config:
  foreach:
    items: "vars.documents"    # expression → must resolve to a list
    as: "item"                 # variable name for the current item
    index_as: "idx"            # optional: variable name for the index
```

- `items` — expression evaluated against execution state; must resolve to a list.
- `as` — injected into the step input as an extra field before each invocation.
- `index_as` — optional, injected as the 0-based iteration index.
- **Output collection**: each output field becomes a list of per-item values.
- If `items` resolves to an empty list, the step produces `{}` (no output).

### Examples

```yaml
# Summarize each document independently
steps:
  - id: summarize_all
    uses: text.content.summarize
    input:
      text: "item"           # resolved per iteration
    output:
      summary: "vars.summaries"
    config:
      foreach:
        items: "vars.documents"
        as: "item"

# Result: vars.summaries = ["summary_1", "summary_2", ...]
```

```yaml
# Score each option with retry per iteration
steps:
  - id: score_options
    uses: eval.option.score
    input:
      option: "item"
      criteria: "vars.criteria"
    output:
      score: "vars.scores"
    config:
      foreach:
        items: "vars.options"
        as: "item"
        index_as: "idx"
      retry:
        max_attempts: 2
        backoff_seconds: 0.5
```

---

## 4. While

Re-execute the capability while a condition holds (bounded).

```yaml
config:
  while:
    condition: "vars.score < 0.8"  # re-evaluated after each iteration
    max_iterations: 10              # required safety bound
```

- The capability executes, its output is applied to state, and the condition
  is re-evaluated.
- If the condition becomes false, the loop stops.
- `max_iterations` is a **mandatory** safety bound (default: 10).
- **Output handling**: each iteration overwrites the previous output. The
  final output is what remains in state.

### Examples

```yaml
# Iteratively refine a summary until quality threshold
steps:
  - id: refine
    uses: text.content.summarize
    input:
      text: "vars.current_text"
      feedback: "vars.last_feedback"
    output:
      result: "vars.current_text"
      score: "vars.score"
    config:
      while:
        condition: "vars.score < 0.9"
        max_iterations: 5
```

```yaml
# Retry extraction until no unknowns remain
steps:
  - id: extract_entities
    uses: data.record.transform
    input:
      data: "vars.raw_data"
      context: "vars.extraction_context"
    output:
      entities: "vars.entities"
      unknowns: "vars.unknown_count"
    config:
      while:
        condition: "vars.unknown_count > 0"
        max_iterations: 3
      retry:
        max_attempts: 2
```

---

## Expression Language

Conditions and `foreach.items` use a safe expression language. **No
`eval()`** — expressions are parsed by a recursive-descent parser.

### Grammar

```
expr       := or_expr
or_expr    := and_expr ('or' and_expr)*
and_expr   := not_expr ('and' not_expr)*
not_expr   := 'not' not_expr | cmp_expr
cmp_expr   := value (op value)?
value      := ref | string | number | bool | null | list | '(' expr ')'
ref        := identifier ('.' identifier)*
list       := '[' (expr (',' expr)*)? ']'
op         := '==' | '!=' | '>' | '<' | '>=' | '<=' | 'in' | 'not in'
```

### Value Types

| Type     | Syntax                           | Example                  |
| -------- | -------------------------------- | ------------------------ |
| String   | Single or double quotes          | `'hello'`, `"world"`     |
| Number   | Integer or float                 | `42`, `3.14`             |
| Boolean  | `true`, `false`                  | `true`                   |
| Null     | `null`, `none`                   | `null`                   |
| List     | Brackets with comma-separated    | `['a', 'b', 'c']`       |
| Ref      | Dotted namespace path            | `vars.score`             |

### Reference Namespaces

References are resolved against the live execution state:

| Namespace      | Source                              |
| -------------- | ----------------------------------- |
| `inputs.*`     | Skill input parameters              |
| `vars.*`       | Mutable variables (step outputs)    |
| `outputs.*`    | Skill output accumulator            |
| `working.*`    | CognitiveState working memory       |
| `frame.*`      | Immutable reasoning frame           |
| `output.*`     | CognitiveState output metadata      |
| `extensions.*` | Extension data                      |

Nested paths are supported: `vars.result.score`, `working.artifacts.summary`.

### Operators

| Category   | Operators                                          |
| ---------- | -------------------------------------------------- |
| Comparison | `==`, `!=`, `>`, `<`, `>=`, `<=`                   |
| Membership | `in`, `not in`                                     |
| Boolean    | `and`, `or`, `not`                                 |

Precedence (lowest to highest): `or` → `and` → `not` → comparison → value.

### Expression Examples

```yaml
# Simple equality
"vars.status == 'approved'"

# Numeric comparison
"vars.score >= 0.8"

# Boolean logic
"vars.is_ready and not vars.is_locked"

# Membership
"inputs.language in ['es', 'en', 'fr']"

# Complex
"(vars.score > 0.7 or vars.override == true) and vars.attempts < 5"

# Nested reference
"vars.result.confidence > 0.9"
```

---

## 5. Router

Dynamic branching — the step evaluates an expression at runtime and selects
which capability to execute based on the result.

```yaml
config:
  router:
    on: "vars.doc_type"              # expression → value to match
    cases:
      invoice: "doc.invoice.parse"
      contract: "doc.contract.analyze"
      email: "doc.email.extract"
    default: "doc.generic.process"   # optional fallback
```

- `on` — expression evaluated against execution state; result is compared to case keys.
- `cases` — map of value → capability_id. Keys are matched as strings.
- `default` — optional fallback capability when no case matches. If omitted and
  no case matches, the step fails with an expression error.
- `step.uses` serves as the nominal capability for planning/linting; the router
  overrides it at runtime.

### Composition with Other Primitives

- **condition + router**: condition gates first. If false, step is skipped before router evaluates.
- **router + retry**: the routed capability is retried on failure.
- **router + foreach**: each iteration re-evaluates `_invoke_once` with the routed capability. The router is evaluated once before the loop starts.
- **router + while**: each iteration uses the routed capability. The router is evaluated once.
- **router + scatter**: mutually exclusive. Use scatter when you need parallel fan-out.

### Examples

```yaml
# Route document processing based on type
steps:
  - id: process_doc
    uses: doc.generic.process    # fallback / planning reference
    input:
      document: "inputs.document"
    output:
      result: "vars.processed"
    config:
      router:
        on: "inputs.doc_type"
        cases:
          invoice: "doc.invoice.parse"
          contract: "doc.contract.analyze"
          receipt: "doc.receipt.extract"
        default: "doc.generic.process"
```

```yaml
# Route with condition gate and retry
steps:
  - id: classify_and_process
    uses: text.content.generate
    input:
      text: "inputs.text"
    output:
      result: "vars.result"
    config:
      condition: "inputs.text != null"
      router:
        on: "vars.classification"
        cases:
          technical: "text.technical.analyze"
          legal: "text.legal.review"
      retry:
        max_attempts: 2
        backoff_seconds: 1.0
```

---

## 6. Scatter-Gather

Fan-out: launch N capabilities **in parallel** on the same input and merge
their results.

```yaml
config:
  scatter:
    capabilities:
      - "text.content.summarize"
      - "analysis.theme.cluster"
      - "analysis.risk.extract"
    merge: "collect"     # collect | concat_lists | first_success
```

- `capabilities` — list of capability IDs to execute in parallel (minimum 2).
- `merge` — strategy to combine results:

| Strategy        | Output shape                                     | Behavior on failure          |
| --------------- | ------------------------------------------------ | ---------------------------- |
| `collect`       | `{capability_id: produced_output, ...}`          | Failed caps absent from dict |
| `concat_lists`  | `{field: [val_a, val_b, ...], ...}`             | Failed caps skipped          |
| `first_success` | Single capability's output (first to succeed)    | All fail → step fails        |

- `step.uses` is ignored when scatter is present.
- Each capability runs in its own thread from a pool sized to the scatter width.

### Composition with Other Primitives

- **scatter** is mutually exclusive with **foreach**, **while**, and **router**.
- **condition + scatter**: condition gates first. If false, step is skipped before scatter launches.
- **retry + scatter**: retry applies to each individual capability in the scatter (independent retry per capability).

### Examples

```yaml
# Parallel analysis — summarize + extract themes + assess risk
steps:
  - id: parallel_analysis
    uses: _scatter          # placeholder, ignored
    input:
      text: "inputs.document"
    output: {}              # scatter output goes to vars via auto-wire or scatter strategy
    config:
      scatter:
        capabilities:
          - "text.content.summarize"
          - "analysis.theme.cluster"
          - "analysis.risk.extract"
        merge: "collect"
```

```yaml
# Race two models — take the first successful response
steps:
  - id: fastest_model
    uses: _scatter
    input:
      prompt: "inputs.prompt"
    output:
      response: "vars.response"
    config:
      scatter:
        capabilities:
          - "text.content.generate"
          - "text.content.generate.v2"
        merge: "first_success"
```

```yaml
# Merge list outputs from multiple extractors
steps:
  - id: extract_all
    uses: _scatter
    input:
      document: "inputs.doc"
    output: {}
    config:
      scatter:
        capabilities:
          - "data.record.extract.financial"
          - "data.record.extract.legal"
        merge: "concat_lists"
      retry:
        max_attempts: 2
        backoff_seconds: 0.5
```

---

## Config Keys Reference

All control-flow keys live under `step.config`:

```yaml
config:
  # Existing keys
  depends_on: [step_a, step_b]   # DAG dependencies
  timeout_seconds: 30            # per-step timeout

  # Control-flow keys
  condition: "<expression>"       # gate
  retry:                          # retry policy
    max_attempts: 3
    backoff_seconds: 1.0
    backoff_multiplier: 2.0
  foreach:                        # collection iteration
    items: "<expression>"
    as: "item"
    index_as: "idx"
  while:                          # conditional loop
    condition: "<expression>"
    max_iterations: 10
  router:                         # dynamic capability branching
    on: "<expression>"
    cases:
      value1: "capability.id.a"
      value2: "capability.id.b"
    default: "capability.id.fallback"
  scatter:                        # parallel fan-out + merge
    capabilities:
      - "capability.id.a"
      - "capability.id.b"
    merge: "collect"              # collect | concat_lists | first_success
```

---

## Interaction with Existing Features

| Feature              | Interaction                                                                          |
| -------------------- | ------------------------------------------------------------------------------------ |
| **DAG scheduler**    | Unchanged. Scheduler dispatches each step once. All iteration is engine-internal.    |
| **Safety gates**     | Pre-gates run once before any iteration. Post-gates run once after all iterations. Scatter runs pre-gates once before fan-out. |
| **Timeout**          | `timeout_seconds` applies to each individual invocation, not the entire iteration.   |
| **fail_fast**        | Skipped steps (`condition=false`) do NOT trigger fail_fast.                          |
| **Output mapping**   | foreach collects outputs as lists. while overwrites each iteration. scatter depends on merge strategy. |
| **Nested skills**    | Support `condition` and `retry`. Do NOT support `foreach`/`while`/`router`/`scatter`. |
| **Circuit breaker**  | Each invocation (including retries) counts as a binding call.                        |
| **Audit/Trace**      | foreach_count, while_iterations, while_exhausted, router_matched, scatter_strategy, scatter_count are included in step meta. |

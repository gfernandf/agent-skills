# Binding Selection — How the Runtime Chooses a Service

## Overview

Every capability in the system is fulfilled by a **binding** — a contract that
connects a capability to a concrete service (OpenAI API, local Python function,
MCP server, etc.).  Most capabilities ship with **two** official bindings:

| Binding type | Protocol | When it shines |
|---|---|---|
| **OpenAI** (`openapi`) | HTTPS → OpenAI Chat / Embeddings | Best quality for LLM-dependent tasks (summarise, classify, translate, generate, etc.) |
| **Python baseline** (`pythoncall`) | In-process function call | Zero external dependencies — works offline, fast, but produces basic results for tasks that truly need an LLM |

The runtime **automatically detects** which credentials are available and
selects the best binding at execution time.  No manual configuration is needed.

---

## Resolution Policy (v2)

When a capability is invoked the resolver walks through the following steps
in order and stops at the first match:

```
1. Local override          .agent-skills/active_bindings.json
       ↓ (if not set)
2. Environment preferred   Auto-detect credentials → pick best binding
       ↓ (if no preference)
3. Official default        policies/official_default_selection.yaml
       ↓ (if not found)
4. Error                   BindingResolutionError
```

### Step 2 — Environment-Preferred Selection

| Condition | Effect |
|---|---|
| `OPENAI_API_KEY` is set and non-empty | Prefer official **OpenAI** bindings (`openapi` protocol, service id contains `openai`). |
| No recognised credential is present | Prefer official **pythoncall** bindings so no external HTTP call is attempted. |

This means:

* **With an API key**: you get full LLM-powered quality for every capability
  that has an OpenAI binding.
* **Without an API key**: you get the local Python baseline automatically — no
  errors, no wasted HTTP calls.

After Step 2 picks the primary binding, the **fallback chain** in the executor
still applies.  If the primary binding fails at runtime (e.g. network error,
rate limit), the executor tries the `fallback_binding_id` declared in the
binding metadata, and finally the official default.

---

## Quick Start

1. Copy `.env.example` → `.env`.
2. Add your OpenAI API key:
   ```
   OPENAI_API_KEY=sk-…
   ```
3. Run any skill — the runtime selects OpenAI bindings automatically.

If you don't set the key the system still works.  Capabilities that depend
heavily on an LLM (summarise, translate, classify, entity extraction, etc.)
will use their Python baseline which produces valid but simplified results.

---

## Overriding the Auto-Detection

If you need to force a specific binding regardless of environment, use the
explicit override mechanism:

```yaml
# .agent-skills/overrides.yaml
overrides:
  - capability_id: text.content.summarize
    binding_id: python_text_summarize   # force local even when key is set
```

Then activate:

```bash
python -m cli.main activate
```

Local overrides always take priority over environment detection and official
defaults.

---

## Python Baselines

Every capability ships with a Python baseline that works without external
services.  For capabilities that are inherently algorithmic (JSON parsing,
text extraction, template rendering, keyword extraction, etc.) the Python
baseline is **full quality** — no LLM needed.

For capabilities where an LLM is the natural fit (summarise, translate,
generate, classify, detect language, embed, extract entities, transform,
extract response) the Python baseline provides a **functional but basic**
implementation:

| Capability | Baseline behaviour |
|---|---|
| `text.content.summarize` | Truncates to first N sentences |
| `text.content.translate` | Returns text unchanged (identity) |
| `text.content.generate` | Echoes the instruction |
| `text.content.classify` | Returns first candidate category |
| `text.content.embed` | Hash-based pseudo-embedding |
| `text.entity.extract` | Regex-based extraction (type = OTHER) |
| `text.language.detect` | Defaults to `en` |
| `text.content.transform` | Wraps text with the goal directive |
| `text.response.extract` | Returns first sentence of context |

### model.* domain baselines

The `model.*` domain has two kinds of capabilities:

**Deterministic (always pythoncall — no LLM needed):**

| Capability | Baseline behaviour |
|---|---|
| `model.output.sanitize` | Regex-based deep PII/harmful/leakage removal |
| `model.prompt.template` | `${var}` substitution with unresolved tracking |

**LLM-dependent (OpenAI preferred when key is set):**

| Capability | Baseline behaviour |
|---|---|
| `model.output.generate` | Mock / OpenAI only (no pythoncall baseline) |
| `model.response.validate` | Structural check: empty fields, non-dict detection |
| `model.embedding.generate` | Hash-based pseudo-embedding (128-dim default) |
| `model.output.classify` | Keyword frequency + field-name heuristics |
| `model.output.score` | Word overlap, sentence length, length ratio proxies |
| `model.risk.score` | Pattern matching for toxicity, bias, injection markers |

These baselines ensure the system never crashes — but for production use with
LLM-dependent capabilities, **setting `OPENAI_API_KEY` is strongly
recommended**.
### agent.* domain baselines

Three agent.* capabilities use OpenAI for production quality but fall back to
deterministic baselines. Two are always pythoncall-only.

| Capability | Baseline behaviour |
|---|---|
| `agent.input.route` | Keyword match against agent names, first-agent fallback |
| `agent.option.generate` | 4 template archetypes (conservative/balanced/aggressive/alternative) |
| `agent.plan.generate` | 3-step stub plan (analyse → execute → verify) |
| `agent.plan.create` | scaffold_service — LLM if available, template otherwise |
| `agent.task.delegate` | Always accepts; returns deterministic delegation_id |
---

## Adding Support for Other Providers

The environment detection mechanism is extensible.  The mapping of env vars
to service preferences lives in `runtime/binding_resolver.py`:

```python
_ENV_SERVICE_PREFERENCES = [
    ("OPENAI_API_KEY", "openai"),
    # ("ANTHROPIC_API_KEY", "anthropic"),  # future
]
```

To add a new provider: create service descriptors, bindings, and append an
entry to this list.  The resolver will prefer that provider's bindings when
the corresponding key is detected.

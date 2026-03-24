# Cross-Repository Architecture

> How `agent-skills` and `agent-skill-registry` fit together.

---

## Two repositories, one system

| Repository | Role | Contents |
|---|---|---|
| **agent-skill-registry** | Source of truth for contracts | Vocabulary, capabilities, skills, catalog, governance tools |
| **agent-skills** | Runtime execution engine | Bindings, services, gateway, CLI, HTTP/MCP exposure, audit |

The registry defines *what* the system can do (contracts).  
The runtime defines *how* it does it (implementations).

---

## Dependency direction

```
agent-skill-registry          agent-skills
┌────────────────────┐        ┌────────────────────────┐
│ vocabulary/        │        │ bindings/official/     │
│   vocabulary.json  │◄───────│   <capability_id>/     │
│   cognitive_types  │        │     python_*.yaml      │
│   safety_vocab     │        │     openapi_*.yaml     │
│                    │        │                        │
│ capabilities/      │◄───────│ official_services/     │
│   *.yaml           │        │   *_baseline.py        │
│                    │        │                        │
│ skills/            │◄───────│ runtime/               │
│   official/        │        │   execution_engine.py  │
│   experimental/    │        │   scheduler.py         │
│                    │        │   audit.py             │
│ catalog/           │        │                        │
│   capabilities.json│        │ customer_facing/       │
│   skills.json      │        │   http_openapi_server  │
│   graph.json       │        │   mcp_tool_bridge      │
│   stats.json       │        │   neutral_api          │
│   governance_*.json│        │                        │
│                    │        │ cli/                   │
│ tools/             │        │   main.py              │
│   validate_*       │        │                        │
│   generate_*       │        │ gateway/               │
│   governance_*     │        │   agent_gateway.py     │
└────────────────────┘        └────────────────────────┘
```

The runtime references capabilities by their ID (e.g., `text.content.summarize`).
Bindings in `agent-skills` map those IDs to concrete service implementations.
The registry is never imported at runtime — it supplies contracts and tooling only.

---

## Key contracts

### Vocabulary (`vocabulary/vocabulary.json`)

Controlled identifiers for domains, nouns, and verbs. Every capability ID must
decompose into valid vocabulary tokens:

```
domain.noun.verb   →   text.content.summarize
domain.verb        →   data.validate (2-segment shorthand)
```

Rules: max 3 segments, each segment from the vocabulary's controlled lists.

### Capabilities (`capabilities/*.yaml`)

Declarative contracts specifying inputs, outputs, execution properties,
optional `cognitive_hints`, and optional `safety` blocks.

### Skills (`skills/<channel>/<domain>/<slug>/skill.yaml`)

Declarative workflows composed of capability steps. Steps reference
capabilities by ID; execution order is encoded in the step list and
optional `config.depends_on`.

### Catalog (`catalog/`)

Machine-readable artifacts generated from capabilities and skills:

- `capabilities.json` — flat list of all capabilities with resolved metadata.
- `skills.json` — flat list of all skills with resolved steps.
- `graph.json` — dependency graph (skill → capabilities, skill → skills).
- `stats.json` — counts by domain, channel, averages.
- `governance_guardrails.json` — skill overlap and metadata quality report.
- `capability_governance_guardrails.json` — semantic family and domain coverage.

---

## Cross-repo CI pin

`agent-skills` CI pins a specific registry commit (`REGISTRY_REF` in
`.github/workflows/smoke.yml`). This ensures runtime tests validate against
a known-good set of contracts.

Pin drift is capped: if the pin falls too many commits behind `origin/main`,
the canary check flags it for update.

See `docs/CROSS_REPO_PIN_POLICY.md` in `agent-skills` for the full update
procedure.

---

## Validation flow

### Registry side (standalone)

```bash
cd agent-skill-registry
python tools/validate_registry.py           # schema + vocabulary compliance
python tools/governance_guardrails.py ...   # skill overlap + metadata quality
python tools/capability_governance_guardrails.py  # semantic families + domain coverage
python tools/enforce_capability_sunset.py   # deprecated capability lifecycle
python tools/generate_catalog.py            # regenerate catalog/*
python tools/registry_stats.py              # regenerate stats.json
```

CI enforces `git diff --exit-code -- catalog` — catalog must be fresh.

### Runtime side (depends on registry contracts)

```bash
cd agent-skills
python test_capabilities_batch.py           # execute all capabilities with test data
python cli/main.py doctor                   # environment health check
python tooling/verify_smoke_capabilities.py # smoke subset
```

---

## Adding a new capability end-to-end

1. **Registry**: create `capabilities/<id>.yaml` following vocabulary rules.
2. **Registry**: add the ID to `capabilities/_index.yaml`.
3. **Registry**: run the full validation + catalog sequence.
4. **Runtime**: create `bindings/official/<id>/` with at least one binding YAML.
5. **Runtime**: implement the service function (or configure an OpenAPI binding).
6. **Runtime**: add test data to `test_capabilities_batch.py` and validate.
7. **Both repos**: commit and push.

---

## Adding a new skill end-to-end

1. **Registry**: ensure all referenced capabilities exist.
2. **Registry**: create `skills/<channel>/<domain>/<slug>/skill.yaml`.
3. **Registry**: run the full validation + catalog sequence.
4. **Runtime**: bindings for each step's capability must already exist.
5. **Runtime**: `cli run <skill_id>` to test execution.
6. **Both repos**: commit and push.

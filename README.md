# Agent Skill Registry

An open registry of reusable **AI agent skills** and **capability definitions**.

The registry provides a standardized, declarative way to define:

- primitive **capabilities**
- composable **skills (workflows)**
- shared **vocabulary**
- machine-readable **catalogs**

It acts as the **source of truth for agent workflows** that can be executed by compatible runtimes.

## Runtime Quality & Observability

- Observability implementation details: `docs/OBSERVABILITY.md`
- Pre-MCP/OpenAPI readiness and consistency snapshot: `docs/PRE_MCP_OPENAPI_READINESS.md`

## Skill Execution Audit Layer

The runtime supports persisted execution audit records per skill run.

- Modes: `off`, `standard`, `full`
- Default mode: `standard` (configurable via `AGENT_SKILLS_AUDIT_DEFAULT_MODE`)
- Default output: `artifacts/runtime_skill_audit.jsonl`

`standard` mode stores lightweight audit metadata and payload hashes.

`full` mode additionally stores redacted payload snapshots.

Surface controls:

- CLI `run` / `trace`: `--audit-mode off|standard|full`
- HTTP `/v1/skills/{id}/execute`: body field `audit_mode`
- MCP `skill.execute`: argument `audit_mode`

User-managed deletion is available via:

- `python cli/main.py audit-purge --trace-id <trace-id>`
- `python cli/main.py audit-purge --skill-id <skill-id>`
- `python cli/main.py audit-purge --older-than-days 30`
- `python cli/main.py audit-purge --all`

## MCP Integration Slice

The runtime now includes initial MCP-backed capability slices without changing
the official default binding selection.

- `text.summarize`
	- Service: `services/official/text_mcp_inprocess.yaml`
	- Binding: `bindings/official/text.summarize/mcp_text_summarize_inprocess.yaml`
- `data.schema.validate`
	- Service: `services/official/data_mcp_inprocess.yaml`
	- Binding: `bindings/official/data.schema.validate/mcp_data_schema_validate_inprocess.yaml`
- `web.fetch`
	- Service: `services/official/web_mcp_inprocess.yaml`
	- Binding: `bindings/official/web.fetch/mcp_web_fetch_inprocess.yaml`

Verifications:

- `python tooling/verify_mcp_text_summarize.py`
- `python tooling/verify_mcp_data_web_slices.py`

This uses an in-process MCP server adapter to validate the runtime MCP path end to end
before broader external MCP service rollout.

## OpenAI Access (Local Runtime)

An experimental official OpenAPI service/binding is available for `text.summarize`
using OpenAI Chat Completions.

- Service: `services/official/text_openai_chat.yaml`
- Binding: `bindings/official/text.summarize/openapi_text_summarize_openai_chat.yaml`
- Verifier: `python tooling/verify_openai_text_summarize.py`

Credentials are resolved from the local environment at runtime:

- `OPENAI_API_KEY`

PowerShell example:

```powershell
$env:OPENAI_API_KEY = "<your-key>"
python tooling/verify_openai_text_summarize.py
```

This flow does not change official default selection yet; it validates access and
binding behavior before capability-by-capability default promotion.

## Binding Fallback Policy (Runtime)

Execution now applies a deterministic fallback chain per capability:

1. Resolved primary binding (user override or official default).
2. Optional `metadata.fallback_binding_id` chain declared by bindings.
3. Mandatory terminal fallback to the official default binding.

Verifier:

- `python tooling/verify_binding_fallback_policy.py`

## Binding Conformance Layer

Bindings may declare metadata profile:

- `conformance_profile: strict|standard|experimental`

Behavior:

- Missing profile defaults to `standard`.
- Invalid profile values are rejected at binding load time.
- Effective profile is exposed in execution metadata for tracing/explainability.
- Optional enforcement is available at execution time using required profile
	(`strict|standard|experimental`).

CLI explain surface:

- `python cli/main.py explain-capability text.summarize`
- `python cli/main.py explain-capability text.summarize --required-conformance-profile strict`

Consumer-facing explain endpoints:

- `POST /v1/capabilities/{capability_id}/explain`
- MCP tool: `capability.explain`

Verifier:

- `python tooling/verify_binding_conformance_layer.py`
- `python tooling/verify_conformance_enforcement.py`
- `python tooling/verify_binding_conformance_suite.py`

Governance discovery surfaces:

- CLI: `python cli/main.py skill-governance --min-state trusted --limit 20`
- HTTP: `GET /v1/skills/governance?min_state=trusted&limit=20`
- MCP tool: `skill.governance.list`

Usage ingestion for governance wiring:

- `python tooling/ingest_skill_usage_from_logs.py --log-file <runtime.jsonl>`

## Skill Governance Catalog (Cold Start + Field Maturity)

The runtime now supports an operational quality catalog that is separate from the
registry source definitions.

- Builder: `python tooling/build_skill_quality_catalog.py`
- Output: `artifacts/skill_quality.json`

Optional evidence inputs (if present):

- `artifacts/skill_lab_validation.json`
- `artifacts/skill_usage_30d.json`
- `artifacts/skill_feedback_30d.json`

Example templates are provided:

- `tooling/examples/skill_lab_validation.example.json`
- `tooling/examples/skill_usage_30d.example.json`
- `tooling/examples/skill_feedback_30d.example.json`

Lifecycle states:

- `draft`
- `validated`
- `lab-verified`
- `trusted`
- `recommended`

Cold-start behavior is explicit: without field usage data, skills can still be
classified using internal evidence and readiness scoring.

## Local-to-Registry Workflow (User UX)

The platform now supports a complete local-first workflow so users can iterate
privately and only request officialization when they are ready.

1. Generate a local skill from plain language:

```powershell
python skills.py scaffold "summarize incoming support email and store summary in memory"
```

2. Prepare a promotion package:

```powershell
python skills.py package-prepare --skill-id text.summarize-incoming-support --target-channel experimental
```

3. Validate package quality and governance readiness:

```powershell
python skills.py package-validate "<package_path>" --print-pr-command
```

4. Launch a PR in one command (after validation):

```powershell
python skills.py package-pr "<package_path>"
```

All package workflow commands support machine-readable output for UI/backend orchestration:

- `python skills.py package-prepare ... --json`
- `python skills.py package-validate ... --json`
- `python skills.py package-pr ... --json`

## Documentation Index

- Current project closure snapshot: `docs/PROJECT_STATUS.md`
- 10-minute onboarding for new contributors: `docs/ONBOARDING_10_MIN.md`
- Runtime runner architecture and operations: `docs/RUNNER_GUIDE.md`
- Observability and trace/redaction controls: `docs/OBSERVABILITY.md`
- Pre-MCP/OpenAPI readiness baseline: `docs/PRE_MCP_OPENAPI_READINESS.md`
- OpenAPI v1 phase-0 governance and technical foundation: `docs/OPENAPI_PHASE0_FOUNDATION.md`
- OpenAPI v1 phase-1 smoke rollout plan: `docs/OPENAPI_PHASE1_SMOKE_PLAN.md`
- OpenAPI construction packages and commit strategy: `docs/OPENAPI_CONSTRUCTION_PACKAGES.md`
- **OpenAPI construction guide (copy-paste templates)**: `docs/OPENAPI_CONSTRUCTION_GUIDE.md`
- **OpenAPI population checklist (gate criteria + regression tests)**: `docs/OPENAPI_POPULATION_CHECKLIST.md`
- **OpenAPI construction phase closure (Package 6 summary)**: `docs/OPENAPI_PACKAGE6_CLOSURE.md`
- OpenAPI error and security baseline: `docs/OPENAPI_ERROR_SECURITY_BASELINE.md`
- **Consumer-facing neutral API (HTTP + MCP adapters)**: `docs/CONSUMER_FACING_NEUTRAL_API.md`
- **MCP integration rollout slices and verification**: `docs/MCP_INTEGRATION_SLICES.md`
- **Skill governance manifesto (trust model + architecture changes)**: `docs/SKILL_GOVERNANCE_MANIFESTO.md`

---

# Why this exists

AI agents increasingly rely on structured tools and workflows.

However, most implementations today are:

- tightly coupled to a specific framework
- implemented imperatively in code
- difficult to reuse across systems
- inconsistent in naming and structure

The **Agent Skill Registry** addresses this by providing:

- a **common vocabulary**
- a **declarative workflow model**
- a **shared registry of reusable skills**
- a **machine-readable catalog for runtimes**

The goal is to make agent capabilities **discoverable, composable, and reusable**.

---

# Core Concepts

The registry defines two fundamental building blocks.

## Capabilities

Capabilities represent **primitive operations**.

They define a **contract** describing what an operation does, including:

- inputs
- outputs
- execution properties
- optional metadata

Examples:

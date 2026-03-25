# Roadmap — agent-skills

> Plan de trabajo para llevar el proyecto a nivel estándar de industria.
> Cada fase tiene entregables concretos y criterios de completitud.

---

## Phase 1 — Community Foundation (bloqueante para adopción)

### 1.1 Community artifacts
- [x] CONTRIBUTING.md — workflow de PR, review SLA, decision process
- [x] CODE_OF_CONDUCT.md — Contributor Covenant v2.1
- [x] ROADMAP.md (este documento)
- [x] GitHub issue templates (bug, feature, RFC)
- [ ] Governance transition plan (single-author → steering committee when contributors join)

### 1.2 Examples & tutorials
- [x] `examples/` directory with 5+ end-to-end skill examples
- [ ] "Build Your First Skill" tutorial (docs/TUTORIAL_FIRST_SKILL.md)
- [ ] Video walkthrough / screencast

### 1.3 Formal schemas
- [ ] JSON Schema exports for: SkillSpec, CapabilitySpec, StepConfig, CognitiveState v1
- [ ] Publish schemas to `docs/schemas/`
- [ ] Auto-validate YAML against schemas in CI

---

## Phase 2 — SDK & Interoperability (bloqueante para viralización)

### 2.1 OpenAPI spec completeness
- [ ] Add SSE streaming endpoint to OpenAPI spec
- [ ] Add async execution endpoints (`/execute/async`, `/v1/runs/*`)
- [ ] Auto-generate OpenAPI from handler (stretch goal)

### 2.2 TypeScript SDK
- [ ] Generate from OpenAPI spec via `openapi-generator-cli`
- [ ] Publish to npm as `@agent-skills/client`
- [ ] Include SSE client helper
- [ ] README with usage examples

### 2.3 Go SDK (stretch)
- [ ] Generate from OpenAPI spec
- [ ] Publish module

### 2.4 Python SDK client
- [ ] Thin wrapper over `requests` for programmatic access
- [ ] Publish as `agent-skills-client` on PyPI

---

## Phase 3 — Enterprise Features

### 3.1 Auth & RBAC
- [ ] JWT/OAuth 2.0 bearer token middleware (pluggable)
- [ ] Role model: `admin`, `operator`, `executor`, `reader`
- [ ] Per-skill permission scoping
- [ ] Multi-tenancy isolation via JWT tenant claim

### 3.2 Webhooks & Events
- [ ] `POST /v1/webhooks` subscription management
- [ ] Event types: `skill.completed`, `skill.failed`, `run.completed`
- [ ] Delivery retry with exponential backoff
- [ ] HMAC signature verification

### 3.3 Persistent storage backends
- [ ] Abstract `RunStore` protocol
- [ ] PostgreSQL backend
- [ ] Redis backend (optional)

### 3.4 Kubernetes
- [ ] Helm chart
- [ ] K8s Operator CRD `AgentSkillsRuntime` (stretch)

---

## Phase 4 — Standards Track

### 4.1 Formal specification
- [ ] JSON Schema for all YAML formats (skills, capabilities, bindings)
- [ ] Protocol Buffers definitions (gRPC)
- [ ] Formal positioning paper: agent-skills vs SCL / SPIRAL / CoALA

### 4.2 Governance maturity
- [ ] Steering committee charter (activate when ≥3 active contributors)
- [ ] RFC process with numbered proposals
- [ ] Contributor ladder: contributor → reviewer → maintainer → lead

### 4.3 Ecosystem growth
- [ ] Community registry federation (multi-org registries)
- [ ] Plugin system with entry_points discovery
- [ ] Marketplace / catalog website

---

## Scoring Target

| Dimension | Current | Target | Phase |
|-----------|:-------:|:------:|:-----:|
| Architecture | 9 | 9 | — |
| Security | 8 | 9 | P3 |
| Specification | 8 | 9 | P1+P4 |
| Performance | 6 | 7 | P3 |
| DX / Onboarding | 5 | 8 | P1 |
| Governance | 3 | 7 | P1+P4 |
| Ecosystem / SDKs | 2 | 8 | P2 |
| Standard features | 4 | 7 | P3 |
| **Overall** | **5.6** | **≥8** | — |

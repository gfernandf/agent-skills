# Skill Governance Manifesto

Date: 2026-03-13
Status: Proposed baseline for implementation
Scope: Product-level trust model for portable skills over abstract capabilities

## 1. Product Thesis

The product must guarantee two things at the same time:

1. Portability:
- Skills are high-level workflows built on abstract capabilities.
- Capability contracts are the source of truth in registry YAML.

2. Trust:
- A skill should not be considered reliable only because it executes.
- Reliability must be evidenced through internal validation and field behavior.

This manifesto defines how to keep portability while controlling quality uncertainty introduced by provider and binding flexibility.

## 2. Non-Negotiable Invariants

1. Source of truth for semantics:
- Capabilities are defined in registry YAML and remain canonical.
- Runtime does not execute from generated catalogs.

2. Separation of concerns:
- Registry catalogs describe and index.
- Operational quality artifacts evaluate behavior and trust.

3. Override safety model:
- User overrides are allowed and encouraged.
- Last-resort fallback must always be the official default binding.

4. Explainability:
- Every effective execution path must be explainable to a human user.

## 3. Capability Leveling Model

Capabilities must be high-level enough for agent composition but narrow enough to minimize hallucination risk.

### 3.1 Risk classes

A. Deterministic operations (low epistemic risk)
- Examples: data.schema.validate, data.json.parse, table.filter.

B. Retrieval operations (medium risk)
- Examples: web.fetch, fs.read, pdf.read.
- Variability comes from source quality and external system behavior.

C. Generative and decision operations (higher risk)
- Examples: text.summarize, text.classify, agent.plan.generate, agent.route.
- Variability comes from model behavior and provider differences.

### 3.2 Design rule

A capability is valid for this product if:

1. It has a clear contract boundary.
2. It can be tested for conformance independent of workflow context.
3. It does not encode provider-specific semantics in its public contract.

## 4. Trust and Quality Model

### 4.1 Two evidence channels

1. Internal evidence (cold-start readiness)
- Contract tests
- Smoke tests
- Human review
- Control point validation

2. Field evidence (product maturity)
- Execution success rates
- Latency profiles
- User ratings
- User reports and severe incidents

### 4.2 Lifecycle states

- draft
- validated
- lab-verified
- trusted
- recommended

Cold-start is explicitly supported: skills can be lab-verified before field usage volume exists.

### 4.3 Scores

- readiness_score: internal evidence
- field_score: production behavior
- overall_score: weighted by sample volume

Weighting model by executions_30d:

- < 20: overall = readiness only
- 20 to 49: readiness-weighted mixed score
- >= 50: field-weighted mixed score

## 5. Mitigating Execution Uncertainty with Portability

Portability introduces backend variance. This is controlled by explicit conformance and routing policy.

### 5.1 Binding conformance profile

Each binding/provider path is tagged by conformance profile:

- strict: strongest contract compliance and deterministic behavior under policy
- standard: acceptable for production with known variance bounds
- experimental: available for opt-in, not default for trusted paths

### 5.2 Runtime selection policy

1. User-selected primary binding executes first.
2. Optional user-defined fallback executes next.
3. Official default binding is mandatory terminal fallback.

### 5.3 Capability assurance contract

For each capability, define:

1. Invariants that must hold across providers.
2. Error taxonomy and normalization rules.
3. Safety constraints and side-effect boundaries.
4. Conformance test vectors and expected outcomes.

## 6. Human UX Guardrails (Critical)

Quality controls must not degrade usability.

### 6.1 No-complexity default experience

If user does nothing:

1. Defaults are ready and executable.
2. Credentials are clearly prompted when needed.
3. Errors are actionable and short.

### 6.2 Optional complexity only when requested

Advanced controls (fallback chains, custom providers, strict profiles) are optional and progressive.

### 6.3 Explainability surfaces

For each capability/skill execution, user can inspect:

1. Effective binding and service.
2. Why it was selected.
3. Fallback path used, if any.
4. Trust state of the skill and evidence source.

### 6.4 Honest trust labels

Always show trust evidence source:

- internal-evidence
- mixed-evidence
- field-evidence

Users must never confuse internal validation with broad field reliability.

## 7. Architecture Changes Required

This section maps the strategy to implementation deltas.

### 7.1 Registry layer (agent-skill-registry)

Keep unchanged as semantic source:

1. Capabilities remain canonical in YAML.
2. Skills remain declarative workflows.
3. Catalog generation remains descriptive.

Additions (non-breaking):

1. Optional metadata conventions for trust-oriented documentation.
2. Governance documentation for lifecycle semantics.

### 7.2 Runtime layer (agent-skills)

Add or extend:

1. Binding conformance metadata and profile enforcement.
2. Deterministic fallback resolution policy with official terminal fallback.
3. Quality ingestion pipeline:
- internal evidence
- usage evidence
- feedback evidence
4. Skill quality catalog generation and exposure.
5. Explainability endpoints or commands for effective path introspection.

### 7.3 Observability layer

Add normalized metrics for quality:

1. success and failure classes by capability and binding
2. latency percentiles by capability and binding
3. fallback activation counts
4. user feedback aggregates

### 7.4 Consumer API and CLI

Add user-centric introspection operations:

1. explain capability resolution
2. explain skill trust state and evidence
3. list recommended and trusted skills with evidence source

## 8. Rollout Plan

Phase 1: Foundation (short)

1. Formalize lifecycle and scoring policy.
2. Publish conformance profile definitions.
3. Keep defaults simple and no-regression for current users.

Phase 2: Assurance and explainability

1. Add capability assurance contracts for prioritized capabilities.
2. Add binding conformance checks.
3. Expose explainability surfaces in CLI/API.

Phase 3: Product trust maturity

1. Ingest real usage and feedback signals.
2. Promote skills from lab-verified to trusted/recommended based on evidence.
3. Use trust states in discovery and routing preferences.

## 9. Success Criteria

1. Users can run defaults without configuration burden.
2. Skills have transparent trust states with clear evidence source.
3. Overrides do not compromise baseline reliability due to terminal default fallback.
4. Trusted and recommended states correlate with real quality outcomes.
5. Portability remains intact while uncertainty is bounded and communicated.

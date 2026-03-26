# CoALA Formal Mapping

This document provides a formal mapping between **Agent Skills Runtime** concepts and the **CoALA** (Cognitive Architectures for Language Agents) framework described in [Sumers et al., 2024](https://arxiv.org/abs/2309.02427).

The mapping is intended for academic reviewers evaluating Agent Skills against established cognitive architecture standards.

---

## Core Architecture Mapping

| CoALA Component | Agent Skills Equivalent | Location | Notes |
|----------------|------------------------|----------|-------|
| **Agent** | Skill (declarative YAML workflow) | `skills/**/*.yaml` | A skill is a complete agent program: inputs, outputs, steps, metadata |
| **Action Space** | Capability Registry (122 capabilities) | `capabilities/*.yaml` | Each capability is a typed action with inputs/outputs contract |
| **Decision Procedure** | DAG Scheduler + Binding Resolver | `runtime/scheduler.py`, `runtime/binding_resolver.py` | Kahn's topological sort determines execution order; resolver selects backend |
| **Memory (Long-term)** | `memory.*` capabilities + external stores | `memory.context.store`, `memory.context.retrieve` | Capabilities for persistent storage/retrieval |
| **Memory (Working)** | `WorkingState` (10 typed cognitive slots) | `runtime/execution_state.py` → `working` | Mutable slots: hypothesis, evidence, context, observations, reasoning_chain, constraints, alternatives, confidence, uncertainty, meta_cognition |
| **Memory (Episodic)** | `TraceState` (per-step lineage + events) | `runtime/execution_state.py` → `trace` | Records reads/writes per step, aggregate metrics, full event log |
| **Perception** | Input mapping + reference resolution | `runtime/input_mapper.py`, `runtime/reference_resolver.py` | `$inputs.*`, `$vars.*`, `$outputs.*`, `$working.*` references |
| **Grounding** | Binding protocols (PythonCall, OpenAPI, MCP, OpenRPC) | `runtime/protocol_router.py` | Same capability, 4 execution backends |

---

## Cognitive State Block Mapping

| CoALA Memory Type | Agent Skills Block | Structure | CoALA Alignment |
|-------------------|-------------------|-----------|-----------------|
| **Semantic memory** | `FrameState` | `goal`, `constraints`, `success_criteria`, `context` | Immutable reasoning context — the "what" and "why" |
| **Working memory** | `WorkingState` | 10 typed slots (see below) | Mutable scratchpad for in-flight reasoning |
| **Procedural memory** | Skill DAG + step definitions | `steps[].uses`, `config.depends_on` | The "how" — encoded as declarative workflow |
| **Episodic memory** | `TraceState` | `step_data_lineage`, `aggregate_metrics` | Runtime execution history |

### WorkingState Cognitive Slots

| Slot | CoALA Role | Type | Purpose |
|------|-----------|------|---------|
| `hypothesis` | Belief state | Summary | Current working hypothesis |
| `evidence` | Evidence accumulator | Entity[] | Supporting evidence collected |
| `context` | Contextual grounding | Context | Active context window |
| `observations` | Perception buffer | Entity[] | Raw observations before synthesis |
| `reasoning_chain` | Inference trace | Plan[] | Step-by-step reasoning log |
| `constraints` | Constraint set | Risk[] | Active constraints and boundaries |
| `alternatives` | Alternative set | Entity[] | Considered alternatives |
| `confidence` | Meta-cognition | Score | Current confidence estimate |
| `uncertainty` | Meta-cognition | Risk | Recognized uncertainty areas |
| `meta_cognition` | Self-model | Narrative | Reflection on own reasoning process |

---

## Cognitive Hints → CoALA Role Mapping

Each capability declares `cognitive_hints.role` that maps to a CoALA processing stage:

| `cognitive_hints.role` | CoALA Stage | Description | Example Capabilities |
|-----------------------|-------------|-------------|---------------------|
| `perceive` | Perception | Convert raw input to structured form | `text.entity.extract`, `audio.speech.transcribe` |
| `analyze` | Internal reasoning | Examine and decompose | `code.source.analyze`, `analysis.problem.split` |
| `evaluate` | Decision making | Score, rank, or judge | `eval.option.score`, `data.schema.validate` |
| `synthesize` | Internal action | Combine information into new form | `text.content.summarize`, `text.content.merge` |
| `act` | External action | Produce side effects | `fs.file.write`, `email.message.send` |
| `retrieve` | Memory retrieval | Access stored knowledge | `memory.context.retrieve`, `research.source.retrieve` |
| `store` | Memory storage | Persist information | `memory.context.store` |
| `plan` | Planning | Generate execution plans | `agent.plan.generate`, `agent.plan.create` |
| `route` | Decision procedure | Select among options | `agent.input.route`, `agent.task.delegate` |
| `monitor` | Meta-cognition | Observe and track execution | `ops.trace.monitor`, `ops.health.check` |

---

## Execution Cycle Mapping

CoALA defines a perception → reasoning → action cycle. Agent Skills implements this as:

```
                   CoALA Cycle                    Agent Skills
                ┌─────────────┐              ┌──────────────────┐
                │  Perceive   │              │  Input Mapper    │
                │  (observe)  │──────────────│  + Reference     │
                └──────┬──────┘              │  Resolver        │
                       │                      └────────┬─────────┘
                       ▼                               ▼
                ┌─────────────┐              ┌──────────────────┐
                │  Reason     │              │  DAG Scheduler   │
                │  (decide)   │──────────────│  + Policy Engine │
                └──────┬──────┘              │  + Safety Gates  │
                       │                      └────────┬─────────┘
                       ▼                               ▼
                ┌─────────────┐              ┌──────────────────┐
                │  Act        │              │  Binding Executor│
                │  (execute)  │──────────────│  + Protocol      │
                └──────┬──────┘              │  Router          │
                       │                      └────────┬─────────┘
                       ▼                               ▼
                ┌─────────────┐              ┌──────────────────┐
                │  Learn      │              │  Output Mapper   │
                │  (update)   │──────────────│  + TraceState    │
                └─────────────┘              │  + CognitiveState│
                                              └──────────────────┘
```

---

## Safety Model → CoALA Guardrails

| CoALA Guardrail Concept | Agent Skills Implementation |
|------------------------|---------------------------|
| Action boundaries | Safety gates (`mandatory_pre_gates`, `mandatory_post_gates`) |
| Trust levels | 4-tier hierarchy: sandbox → standard → elevated → privileged |
| Human-in-the-loop | `requires_confirmation` flag + `SafetyConfirmationRequiredError` |
| Scope constraints | `scope_constraints` in capability safety block |
| Side-effect tracking | `properties.side_effects` flag per capability |

---

## Differences from Pure CoALA

| Aspect | CoALA (theoretical) | Agent Skills (practical) |
|--------|-------------------|------------------------|
| Agent definition | Programmatic | Declarative YAML |
| Memory implementation | Abstract | Concrete typed slots + merge strategies |
| Action space | Open-ended | Governed registry with conformance profiles |
| Grounding | Not specified | 4-protocol binding with automatic fallback |
| Safety | Not formal | 4-tier gate system with policy engine |
| Observability | Not covered | OTel + audit + metrics built-in |

---

## References

- Sumers, T.R., et al. (2024). "Cognitive Architectures for Language Agents." *arXiv:2309.02427*.
- Agent Skills CognitiveState v1: `docs/COGNITIVE_STATE_V1.md`
- Safety model: `docs/SECURITY.md`
- DAG Scheduler: `docs/SCHEDULER.md`

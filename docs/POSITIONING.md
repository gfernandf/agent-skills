# Positioning: agent-skills vs Related Frameworks

> How agent-skills relates to SCL, SPIRAL, CoALA, and other agent capability frameworks.

## Overview

agent-skills occupies a specific niche: **deterministic, composable skill
execution over abstract capability contracts**. This document positions it
relative to related frameworks in the AI agent ecosystem.

## Comparison Matrix

| Dimension | agent-skills | SCL (Skill Composition Language) | SPIRAL | CoALA |
|-----------|-------------|----------------------------------|--------|-------|
| **Primary focus** | Deterministic execution of composable skills | Skill composition DSL | Agent learning and adaptation | Cognitive agent architecture |
| **Execution model** | DAG scheduler with binding resolution | Declarative composition | Adaptive execution | Cognitive loop |
| **Abstraction level** | Capability contracts (YAML) | Skill templates | Learning objectives | Cognitive modules |
| **Multi-provider** | Yes (binding protocol: pythoncall, openapi, mcp, llmcall) | No | No | No |
| **Fallback chains** | Built-in (conformance profiles) | Not applicable | Not applicable | Not applicable |
| **Schema validation** | Contract-first (16 JSON Schemas) | Template-based | None | None |
| **Runtime overhead** | Minimal (in-process, no server required) | Varies | Varies | Varies |
| **Governance** | Full (vocabulary control, lifecycle, sunset) | None | None | None |
| **Multi-surface** | HTTP, MCP, SDK, LLM adapters, gRPC (proto) | Single interface | API | API |

## Key Differentiators

### 1. Capability Abstraction

agent-skills separates **what** (capability contracts) from **how** (bindings
and services). A skill that calls `text.content.summarize` works whether the
backend is a Python function, an OpenAI API call, an MCP tool, or a custom
microservice. No other framework offers this level of backend portability.

### 2. Contract-First Design

Every capability has a YAML contract with typed inputs/outputs, validated by
JSON Schema. Skills compose capabilities into DAGs with data wiring between
steps. This contract-first approach enables:

- Static validation before execution
- IDE auto-completion via JSON Schema
- Automated compatibility checks on contract changes
- SDK generation from contracts

### 3. Deterministic Execution

Unlike agent frameworks that rely on LLM reasoning to select tools, agent-skills
executes a pre-defined DAG. The LLM is used within steps (via bindings), but the
orchestration is deterministic. This provides:

- Predictable latency and behavior
- Reproducible results for the same inputs
- Auditability (full execution trace)
- Testability (mock any binding layer)

### 4. Governance at Scale

The registry governance model (vocabulary control, admission policies, overlap
detection, sunset lifecycle) is designed for organizational use where
uncontrolled skill proliferation becomes a maintenance burden.

## When to Use What

| Scenario | Recommended |
|----------|-------------|
| Building reliable, testable AI workflows | **agent-skills** |
| Researching adaptive agent behaviors | SPIRAL, CoALA |
| Composing skills in a research DSL | SCL |
| Building cognitive agent architectures | CoALA |
| Running skills across multiple LLM providers | **agent-skills** |
| Enterprise deployment with RBAC and audit | **agent-skills** |

## Complementary Usage

agent-skills is not a replacement for agent reasoning frameworks. It can be
used **within** a CoALA-style cognitive loop as the execution engine for
deterministic sub-tasks, while the agent's reasoning layer handles planning
and adaptation.

```
CoALA Agent Loop
  ├── Perceive → (agent-skills: data extraction capabilities)
  ├── Think    → (LLM reasoning, planning)
  ├── Act      → (agent-skills: deterministic skill execution)
  └── Learn    → (SPIRAL: adaptive improvement)
```

## References

- **SCL**: Skill Composition Language — compositional skill definitions
- **SPIRAL**: Systematic Procedures for Iterative Reasoning and Learning
- **CoALA**: Cognitive Architectures for Language Agents (Sumers et al., 2023)
- **MCP**: Model Context Protocol (Anthropic) — tool protocol
- **OpenAI Function Calling**: Tool use protocol for ChatGPT

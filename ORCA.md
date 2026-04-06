# ORCA: Open Cognitive Runtime Architecture

## 1. Introduction

Modern AI agents are predominantly built around **prompt-driven execution**: a model receives instructions, optionally calls tools, and produces outputs based on implicit reasoning hidden within the model.

While effective for simple tasks, this paradigm presents fundamental limitations:

- Opaque reasoning and lack of inspectability
- Fragile and non-deterministic behavior
- Unsafe interaction with external systems
- Limited composability and reuse
- Difficulty in testing, auditing, and governing execution

**ORCA (Open Cognitive Runtime Architecture)** proposes a different approach.

> ORCA defines a standard for building agents as **structured execution systems**, where reasoning, decisions, and actions are explicit, composable, and governable.

---

## 2. The Problem with Prompt-Driven Agents

Current agent systems rely heavily on:

- Implicit reasoning inside LLMs
- Ad-hoc tool calling
- Unstructured intermediate state
- Weak or externalized safety mechanisms

This leads to systems that are:

| Limitation | Impact |
|-----------|--------|
| Hidden reasoning | Impossible to debug or audit |
| Non-determinism | Hard to reproduce behavior |
| Tool misuse | Risk of unsafe actions |
| Tight coupling | Low reuse across systems |
| Prompt complexity | Hard to maintain and scale |

---

## 3. The ORCA Model

ORCA introduces a **Cognitive Execution Layer** between agents and external systems.

### 3.1 Cognitive State

- Frame — context, goals, constraints
- Working — intermediate reasoning artifacts
- Output — final results
- Trace — execution lineage

### 3.2 Capabilities (Contracts)

Atomic operations with explicit inputs/outputs, independent of execution backend.

### 3.3 Skills (Execution Graphs)

Declarative workflows (DAGs) composing capabilities.

### 3.4 Safety Layer

- Trust levels
- Validation gates
- Human confirmation
- Scope constraints

---

## 4. Core Principles

1. Execution over prompting  
2. Explicit state over implicit context  
3. Contracts over conventions  
4. Separation of intent and execution  
5. Safety as a first-class concern  

---

## 5. Architecture Overview

Agent → ORCA Layer → Capabilities → Bindings → Services

---

## 6. Reference Implementation

Agent Skills Runtime is a reference implementation of ORCA.

---

## 7. Vision

ORCA enables:

- Reproducible agents
- Safe execution
- Composable intelligence
- Interoperable ecosystems

---

## 8. Conclusion

ORCA shifts agent design:

From prompt-driven → to execution-driven systems.

---

## 📄 Research Paper

The formal foundations of ORCA are described in:

> Fernandez Alvarez, G. E. (2026). *Beyond Prompting: Decoupling Cognition from Execution in LLM-based Agents through the ORCA Framework*. Zenodo. [https://doi.org/10.5281/zenodo.19438943](https://doi.org/10.5281/zenodo.19438943)

📥 [Download PDF](docs/papers/orca_paper_final_clean_v2.pdf) · 📖 [Full paper page](docs/PAPER.md)


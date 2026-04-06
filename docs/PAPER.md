# 📄 Research Paper

<p align="center">
  <a href="https://doi.org/10.5281/zenodo.19438943"><img src="https://zenodo.org/badge/DOI/10.5281/zenodo.19438943.svg" alt="DOI"></a>
</p>

## Beyond Prompting: Decoupling Cognition from Execution in LLM-based Agents through the ORCA Framework

**Guillermo E. Fernandez Alvarez** · 2026

---

### Abstract

Modern AI agents are predominantly built around prompt-driven execution, where reasoning remains implicit inside the model and tool orchestration lacks formal structure. This paper introduces **ORCA (Open Cognitive Runtime Architecture)**, a framework that decouples cognitive processes from execution mechanics in LLM-based agents. ORCA defines a Cognitive Execution Layer where agent behavior is expressed through **composable capability contracts**, **declarative skill graphs (DAGs)**, and **explicit cognitive state** — replacing ad-hoc prompting with structured, inspectable, and governable execution.

The paper presents Agent Skills Runtime as a reference implementation of ORCA, demonstrating that deterministic execution of agent workflows is achievable without sacrificing flexibility. The architecture supports four binding protocols (PythonCall, OpenAPI, MCP, OpenRPC), ships 122 governed capabilities with zero-config Python baselines, and provides formal alignment with the CoALA cognitive architecture framework.

Key contributions include: (1) a formal separation of intent, cognition, and execution in agent systems; (2) a contract-first capability model with multi-protocol binding resolution; (3) a typed cognitive state (CognitiveState v1) aligned with CoALA; and (4) empirical evidence that structured execution outperforms prompt-driven approaches in reproducibility, safety, and observability.

---

### Key Contributions

| # | Contribution | Impact |
|---|-------------|--------|
| 1 | **Cognition–Execution Separation** | Agents reason through explicit state, not implicit prompts |
| 2 | **Contract-First Capabilities** | Backend-agnostic operations with multi-protocol binding |
| 3 | **CognitiveState v1** | Typed Frame/Working/Output/Trace aligned with CoALA |
| 4 | **Safety-First Execution** | 4-tier trust model with validation gates and scope constraints |
| 5 | **Empirical Evaluation** | Reproducibility, safety, and observability benchmarks |

---

### Download

📥 **[Download PDF](papers/orca_paper_final_clean_v2.pdf)**

---

### Citation

If you use ORCA or Agent Skills Runtime in your research, please cite:

#### APA 7

> Fernandez Alvarez, G. E. (2026). Beyond Prompting: Decoupling Cognition from Execution in LLM-based Agents through the ORCA Framework. *Zenodo*. [https://doi.org/10.5281/zenodo.19438943](https://doi.org/10.5281/zenodo.19438943)

#### BibTeX

```bibtex
@article{fernandez_orca_2026,
  author    = {Fernandez Alvarez, Guillermo E.},
  title     = {Beyond Prompting: Decoupling Cognition from Execution in
               LLM-based Agents through the ORCA Framework},
  year      = {2026},
  publisher = {Zenodo},
  doi       = {10.5281/zenodo.19438943},
  url       = {https://doi.org/10.5281/zenodo.19438943}
}
```

#### Chicago

> Fernandez Alvarez, Guillermo E. 2026. "Beyond Prompting: Decoupling Cognition from Execution in LLM-based Agents through the ORCA Framework." Zenodo. [https://doi.org/10.5281/zenodo.19438943](https://doi.org/10.5281/zenodo.19438943).

---

### Related Resources

| Resource | Description |
|----------|-------------|
| [ORCA Specification](../ORCA.md) | The full ORCA architecture spec |
| [CoALA Mapping](COALA_MAPPING.md) | Formal alignment with CoALA cognitive architecture |
| [Positioning](POSITIONING.md) | Comparison with SCL, SPIRAL, CoALA, and other frameworks |
| [Agent Skills Runtime](https://github.com/gfernandf/agent-skills) | Reference implementation |
| [Agent Skill Registry](https://github.com/gfernandf/agent-skill-registry) | Capability & skill registry |

---

### How to Cite the Software

For citing the runtime software itself (not the paper), use:

```bibtex
@software{fernandez_agent_skills_2026,
  author    = {Fernandez Alvarez, Guillermo},
  title     = {Agent Skills Runtime},
  year      = {2026},
  url       = {https://github.com/gfernandf/agent-skills},
  version   = {0.1.0},
  license   = {Apache-2.0}
}
```

GitHub also provides a "Cite this repository" button powered by [`CITATION.cff`](../CITATION.cff).

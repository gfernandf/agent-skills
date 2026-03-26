# Contributing to agent-skills

Thank you for your interest in contributing! This guide explains how to
propose changes, the review process, and what to expect.

---

## Quick Start

```bash
git clone https://github.com/gfernandf/agent-skills.git
cd agent-skills
python -m pip install -e ".[dev]"
python -m pytest runtime/ -x -q          # all tests must pass
```

---

## How to Contribute

### Bug reports & feature requests

Open a [GitHub Issue](https://github.com/gfernandf/agent-skills/issues)
using the appropriate template (bug / feature / RFC).

### Code contributions

1. **Fork** the repo and create a branch from `main`.
2. **Implement** your change — keep PRs focused on a single concern.
3. **Add tests** — every behavioral change needs at least one test.
4. **Run the full suite**: `python -m pytest runtime/ -x -q`
5. **Open a PR** against `main` with a clear description.

### Skill / capability contributions (registry)

See [agent-skill-registry CONTRIBUTING](https://github.com/gfernandf/agent-skill-registry/blob/main/CONTRIBUTING.md)
and the [Skill Admission Policy](https://github.com/gfernandf/agent-skill-registry/blob/main/docs/SKILL_ADMISSION_POLICY.md).

---

## Project Structure

```
agent-skills/                  ← This repo: execution runtime
├── runtime/                   ← Core engine
│   ├── models.py              ← ExecutionState, CognitiveState v1 dataclasses
│   ├── execution_engine.py    ← Main execution loop
│   ├── scheduler.py           ← DAG scheduler (Kahn's topological sort)
│   ├── policy_engine.py       ← Safety gates, trust levels, confirmation
│   ├── binding_resolver.py    ← Protocol routing + fallback chain
│   ├── *_invoker.py           ← Protocol invokers (OpenAPI, MCP, OpenRPC, PythonCall)
│   ├── checkpoint.py          ← State serialization / restore
│   └── test_*.py              ← Unit tests (175+)
├── gateway/                   ← Skill discovery, ranking, governance
├── customer_facing/           ← HTTP server, neutral API, FastAPI adapter
├── sdk/                       ← Framework adapters (LangChain, CrewAI, AutoGen, SK) + TypeScript SDK
├── bindings/official/         ← 163 binding YAMLs (PythonCall, OpenAPI, MCP)
├── official_services/         ← 25 Python baseline modules (deterministic, no LLM)
├── skills/local/              ← Ready-to-run skill definitions
├── services/official/         ← Service descriptors (endpoints, auth)
├── customization/             ← User override layer
├── policies/                  ← Safety & admission policies
├── cli/                       ← CLI entry point (run, describe, discover, list, attach)
├── tooling/                   ← Validators, verifiers, load tests (k6)
├── examples/                  ← Runnable example skills + client usage
└── docs/                      ← 42 documentation files

agent-skill-registry/          ← Companion repo: canonical definitions
├── capabilities/              ← 122 capability contracts (YAML)
├── skills/                    ← 35 skill definitions
├── vocabulary/                ← Controlled vocabulary, domains, naming
├── catalog/                   ← Generated governance artifacts
└── tools/                     ← Registry validation & generation
```

---

## Review Process

| Stage | SLA | Who |
|-------|-----|-----|
| Triage | 3 business days | Maintainers |
| Review | 5 business days | Maintainers / reviewers |
| Merge | After approval + CI green | Maintainer |

- All PRs require CI to pass (tests, lint, governance checks).
- Breaking changes require an RFC issue first.
- Maintainers may request changes; please respond within 10 days or
  the PR may be closed (you can re-open it later).

---

## Coding Standards

- **Python ≥ 3.11** — use type hints on public APIs.
- **No `eval()` / `exec()`** — safety-critical codebase.
- **Test pattern**: `runtime/test_*.py` using `_test(label, condition)` + `main()`.
- **Structured logging**: use `log_event()` from `runtime.observability`.
- **Security**: follow OWASP Top 10 — validate at boundaries, redact secrets.

---

## Commit Messages

Use conventional-ish messages:

```
feat: add webhook delivery retry
fix: correct rate-limit bypass via X-Forwarded-For
docs: update DEPLOYMENT.md with Helm chart
test: add property-based scheduler tests
```

---

## Decision Making

Currently the project has a single maintainer (@gfernandf). Decision
authority follows this model:

- **Patches / bug fixes**: merged by any maintainer after review.
- **New features**: require an issue discussion before implementation.
- **Breaking changes / architecture**: require an RFC issue with ≥7 day
  comment period.
- **Governance changes**: require explicit maintainer approval.

As the contributor base grows, the project will transition to a
**steering committee model** — see [ROADMAP.md](ROADMAP.md) Phase 4.

---

## Contributor Ladder

| Role | Responsibilities | How to earn |
|------|-----------------|-------------|
| **Contributor** | Submit PRs, report issues | First merged PR |
| **Reviewer** | Review PRs, triage issues | 5+ quality reviews |
| **Maintainer** | Merge PRs, release, architecture | Sustained contribution + invitation |

---

## License

By contributing you agree that your contributions will be licensed under
the [Apache 2.0 License](LICENSE).

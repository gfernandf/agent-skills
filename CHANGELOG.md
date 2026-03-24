# Changelog

All notable changes to **agent-skills** are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.1.0] — 2026-03-24

### Added

#### Phase 0 — Security hardening
- SSRF guard in `runtime/openapi_invoker.py`: URL validation, blocked schemes
  (only http/https), cloud metadata IP blocklist, private-network controls.
- LFI protection in `official_services/fs_baseline.py`: `os.path.realpath`
  canonicalization + boundary check against `AGENT_SKILLS_FS_ROOT`.
- Credential redaction in `runtime/audit.py`: recursive sanitizer replaces
  values whose key contains sensitive terms (`password`, `token`, `secret`, …)
  with `[REDACTED]`.
- Body size limit (2 MB) and per-client rate limiter with stale-entry GC in
  `customer_facing/http_openapi_server.py`.
- Header redaction in `runtime/openapi_invoker.py` for `Authorization`,
  `x-api-key`, `cookie`, and related headers.

#### Phase 1 — Packaging & documentation
- `pyproject.toml` with pip-installable package `agent-skills[all]`.
- `LICENSE` (Apache-2.0), `.env.example`, `docs/INSTALLATION.md`.
- Missing `__init__.py` files added to `runtime/`, `cli/`, `customization/`.
- CI `smoke.yml` updated to `pip install -e ".[all]"`.
- README expanded with architecture diagram and quickstart.

#### Phase 2 — Runtime robustness
- Exponential-backoff retry for transient HTTP errors (429/502/503/504) in
  `runtime/openapi_invoker.py`. Defaults: 3 retries, 1 s / 2 s / 4 s.
  Honors `Retry-After` header (capped at 60 s). Configurable per binding via
  `retry_count`, `retry_backoff_base`, `retry_backoff_factor`.
- Per-step timeout in `runtime/execution_engine.py`: default 60 s, overridable
  per step via `step.config.timeout_seconds`. Raises `StepTimeoutError`.
- Cross-platform file locking (`msvcrt` / `fcntl`) for audit writes; atomic
  purge via `tempfile` + `os.replace`.
- Configurable worker pool via `AGENT_SKILLS_MAX_WORKERS` env var in
  `runtime/scheduler.py`.

#### Phase 3 — Registry hygiene (in agent-skill-registry)
- 52 stub capabilities marked `draft`.
- `validate_registry.py` accepts `draft` status.
- `registry_stats.py` emits `by_status` breakdown.

#### text.* domain review
- New capability bindings: `text.content.generate`, `text.content.transform`,
  `text.response.extract`, `text.content.embed` (OpenAI embeddings).
- Python baselines: `generate_text()`, `rewrite_text()`, `answer_question()`.
- Test harness (`test_capabilities_batch.py`): smart fallback to locally
  importable Python baselines; test data for all 13 text.* capabilities.
- `.gitignore`: `*.egg-info/`.

#### web.* domain review
- 5/5 web.* capabilities verified functional; promoted to `experimental`.
- New bindings: `web.page.scrape`, `web.search.query`, `web.link.extract`,
  `web.content.download`, `web.feed.parse` — OpenAI + pythoncall variants.
- Python baselines in `official_services/web_baseline.py`.
- Default selections added to `policies/official_default_selection.yaml`.

#### Binding auto-detection (Option B)
- `runtime/binding_resolver.py` v2: three-step resolution —
  local override → environment-preferred → official default → error.
- `_resolve_environment_preferred()` checks `_ENV_SERVICE_PREFERENCES`
  for env var availability (e.g. `OPENAI_API_KEY` → prefer `openai` bindings,
  absent → prefer `pythoncall` baselines).
- `ResolvedBinding.selection_source` extended with `environment_preferred`.
- `docs/BINDING_SELECTION.md` created with architecture, resolution flow,
  precedence rules, and per-domain baseline tables.

#### model.* domain implementation
- 6 new capability bindings fleshed out: `model.embedding.generate`,
  `model.output.classify`, `model.output.score`, `model.output.sanitize`,
  `model.prompt.template`, `model.risk.score`.
- 10 binding YAMLs: 6 pythoncall + 4 OpenAI (generate, validate, embed,
  classify).
- Python baselines in `official_services/model_baseline.py`: 7 functions
  (`validate_response`, `generate_embedding`, `classify_output`,
  `score_output`, `sanitize_output`, `template_prompt`, `score_risk`).
- Default selections for all 8 model.* capabilities in
  `policies/official_default_selection.yaml`.

#### Documentation closure
- `docs/BINDING_SELECTION.md` updated with model.* and agent.* baselines tables.

#### agent.* domain review
- 3 draft capabilities fleshed out: `agent.input.route`, `agent.plan.generate`,
  `agent.task.delegate` — enriched contracts with structured inputs/outputs.
- Bindings updated to match new capability schemas (query/agents for route,
  context/max_steps for plan.generate, structured task for delegate).
- Baselines updated: `route_agent()` with keyword matching, `generate_plan()`
  with structured output (steps/assumptions/risks), `delegate_agent()` with
  delegation_id.
- Test data added for `agent.option.generate` and `agent.plan.create`.
- `docs/BINDING_SELECTION.md` updated with agent.* baselines section.

#### Runtime fix — optional input field handling
- `runtime/request_builder.py`: bindings referencing optional input fields
  (absent from step input) no longer raise `RequestBuildError`. Missing fields
  are omitted from pythoncall payloads and rendered as empty in template strings.
  Fixes execution failures for all capabilities with optional inputs.

#### eval.* domain review
- `eval.output.score` bindings updated: context input, quality_level output.
- `eval_baseline.py`: `score_output()` now accepts `context`, returns
  `quality_level` (excellent/good/fair/poor).
- Test data added for `eval.option.analyze` and `eval.option.score`.
- Functional: 54/114 capabilities (up from 52).

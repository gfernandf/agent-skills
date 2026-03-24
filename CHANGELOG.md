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

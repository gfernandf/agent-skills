# Agent Trace Dry Run Guide

This guide documents how `agent.trace` works in practice, how to run it in cycles,
and how to interpret control outcomes (`ok` vs `blocked`) using realistic scenarios.

## 1) What the skill does

`agent.trace` is an incremental control skill for agent execution.

Per cycle it:

1. Validates incoming runtime events.
2. Analyzes execution state and emits structured trace artifacts.
3. Monitors thresholds and returns control signals.

Main outputs used by orchestrators:

- `updated_trace_state`
- `trace_session_id`
- `decision_graph`
- `assumptions`
- `alternative_paths`
- `risk_candidates`
- `confidence`
- `control_status`
- `risk_flags`
- `alerts`

## 2) Execution model (important)

Cycles are not hardcoded in the skill.

- The skill contract is stable.
- The orchestrator decides how many cycles to run.
- State continuity is external via `trace_state` + `trace_session_id`.

Typical pattern:

1. Call cycle N with new `events`.
2. Read `updated_trace_state`.
3. Call cycle N+1 using previous state/session.
4. Use `control_status` to continue, replan, or stop.
5. End with `mode: finalize`.

## 3) Local instance model used in this project

This project runs trace dry-runs using a local host instance under artifacts:

- Local service config: `artifacts/trace-instance/.agent-skills/services.yaml`
- Local active bindings: `artifacts/trace-instance/.agent-skills/active_bindings.json`
- Local analyze binding: `artifacts/trace-instance/.agent-skills/bindings/local/ops.trace.analyze/python_ops_trace_analyze_openai_local.yaml`
- Local monitor binding: `artifacts/trace-instance/.agent-skills/bindings/local/ops.trace.monitor/python_ops_trace_monitor_local.yaml`
- Local implementation: `artifacts/trace-instance/modules/local_instance/trace_openai_service.py`

This keeps experimentation instance-scoped and avoids modifying official runtime services.

## 4) NPM dry-run scripts

Directory:

- `artifacts/trace-instance/npm-dry-run/`

Scripts:

- `npm run dry-run`: baseline risk scenario
- `npm run dry-run:mitigated`: mitigation scenario
- `npm run dry-run:real-agent`: uses OpenAI to generate iterative recommendations and feeds each step into `agent.trace`

PowerShell launcher (same terminal where your OpenAI key is already active):

```powershell
$env:PATH="C:\Program Files\nodejs;" + $env:PATH
& "C:\Program Files\nodejs\npm.cmd" run dry-run --prefix "c:\Users\Usuario\agent-skills\artifacts\trace-instance\npm-dry-run"
& "C:\Program Files\nodejs\npm.cmd" run dry-run:mitigated --prefix "c:\Users\Usuario\agent-skills\artifacts\trace-instance\npm-dry-run"
& "C:\Program Files\nodejs\npm.cmd" run dry-run:real-agent --prefix "c:\Users\Usuario\agent-skills\artifacts\trace-instance\npm-dry-run"
```

## 5) Baselines captured

Blocked baseline snapshot:

- `artifacts/trace-instance/npm-dry-run/baselines/2026-03-15-openai-blocked-v1/`

Mitigated baseline snapshot:

- `artifacts/trace-instance/npm-dry-run/baselines/2026-03-15-openai-mitigated-v1/`

Real-agent blocked baseline snapshot:

- `artifacts/trace-instance/npm-dry-run/baselines/2026-03-15-openai-real-agent-blocked-v1/`

Each baseline folder includes:

- `cycle1.input.json`, `cycle1.output.json`
- `cycle2.input.json`, `cycle2.output.json`
- `cycle3.input.json`, `cycle3.output.json`
- `baseline_summary.json`

## 6) How to read outcomes

`control_status` is a control decision, not just analytics.

- `blocked`: execution should replan before continuing.
- `ok`: execution can proceed under configured thresholds.

`risk_flags` can still exist when status is `ok`.
This means risk is present but currently within allowed threshold policy.

## 7) Observed behavior in this project

Baseline scenario:

- Session continuity preserved across cycles.
- Risk persisted and final status remained `blocked`.

Mitigated scenario:

- Session continuity preserved across cycles.
- Added mitigation events and validation evidence.
- Final status moved to `ok` while still exposing non-zero risk flags.

Real-agent scenario (OpenAI-generated steps):

- Session continuity preserved across all 3 cycles.
- `analysis_source` stayed in `openai` mode across cycles.
- Final status remained `blocked`, with persistent risk flags requiring governance replan.

This is expected and desirable for governance: no hidden risk, but controlled progression.

## 8) Recommended operational policy

For first production usage:

1. Treat `blocked` as mandatory replan.
2. Require explicit mitigation evidence events before retry.
3. Persist cycle inputs/outputs for audit trails.
4. Keep thresholds explicit per scenario instead of relying on implicit defaults.

## 9) Known constraints

- If OpenAI key is missing in the running process, analysis falls back to heuristic mode.
- Node/npm must be available in PATH (or launched via absolute executable path on Windows).
- On Windows, real-agent subprocesses should force UTF-8 (`PYTHONIOENCODING=utf-8`, `PYTHONUTF8=1`) to avoid Unicode print errors in multi-cycle runs.
- The local trace service is instance-scoped under artifacts and intended for controlled experiments before official promotion.

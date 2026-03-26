#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


DEFAULT_PROMPT = (
    "Analiza si el precio del petroleo subira en los proximos dias y haz un trace "
    "de todas tus operaciones usando skills disponibles para ello."
)


def _mcp_call(
    runtime_root: Path,
    registry_root: Path,
    host_root: Path,
    requests: list[dict[str, Any]],
    env: dict[str, str] | None = None,
) -> dict[str, dict[str, Any]]:
    cmd = [
        sys.executable,
        str(runtime_root / "tooling" / "run_customer_mcp_bridge.py"),
        "--runtime-root",
        str(runtime_root),
        "--registry-root",
        str(registry_root),
        "--host-root",
        str(host_root),
    ]
    lines = "\n".join(json.dumps(r, ensure_ascii=False) for r in requests) + "\n"
    cp = subprocess.run(
        cmd,
        input=lines,
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )
    if cp.returncode != 0:
        raise RuntimeError(
            "MCP bridge execution failed.\n"
            f"return_code={cp.returncode}\n"
            f"stdout:\n{cp.stdout}\n"
            f"stderr:\n{cp.stderr}"
        )

    by_id: dict[str, dict[str, Any]] = {}
    for line in cp.stdout.splitlines():
        raw = line.strip()
        if not raw.startswith("{"):
            continue
        try:
            payload = json.loads(raw)
        except Exception:
            continue
        if isinstance(payload, dict) and "id" in payload:
            by_id[str(payload["id"])] = payload
    return by_id


def _select_target_ref(runtime_root: Path, target_ref: str | None) -> str:
    if target_ref:
        return target_ref

    index_path = runtime_root / "artifacts" / "attach_targets" / "index.json"
    if not index_path.exists():
        raise RuntimeError(
            "attach target index not found. Run tooling/build_attach_target_index.py first "
            "or pass --target-ref explicitly."
        )

    payload: Any = json.loads(index_path.read_text(encoding="utf-8"))
    output_ids = (
        payload.get("targets", {}).get("output", [])
        if isinstance(payload, dict)
        else []
    )
    if not isinstance(output_ids, list) or not output_ids:
        raise RuntimeError(
            "No output targets available in artifacts/attach_targets/index.json"
        )

    chosen = output_ids[-1]
    if not isinstance(chosen, str) or not chosen:
        raise RuntimeError("Invalid target_ref selected from attach target index")
    return chosen


def _build_trace_events(
    primary_execution: dict[str, Any], prompt: str, main_skill_id: str
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    trace_id = primary_execution.get("trace_id")
    status = primary_execution.get("status")

    events.append(
        {
            "type": "agent.goal.received",
            "timestamp": "2026-03-16T13:00:00Z",
            "data": {"prompt": prompt},
        }
    )
    events.append(
        {
            "type": "agent.skill.primary_selected",
            "timestamp": "2026-03-16T13:00:01Z",
            "data": {"skill_id": main_skill_id},
        }
    )

    raw_events = primary_execution.get("events", [])
    if isinstance(raw_events, list):
        for idx, item in enumerate(raw_events):
            if not isinstance(item, dict):
                continue
            evt_type = (
                item.get("type") if isinstance(item.get("type"), str) else "unknown"
            )
            ts = (
                item.get("timestamp")
                if isinstance(item.get("timestamp"), str)
                else None
            )
            step_id = (
                item.get("step_id") if isinstance(item.get("step_id"), str) else None
            )
            events.append(
                {
                    "type": f"primary.{evt_type}",
                    "timestamp": ts or f"2026-03-16T13:00:{10 + idx:02d}Z",
                    "data": {"step_id": step_id, "trace_id": trace_id},
                }
            )

    events.append(
        {
            "type": "agent.primary.completed",
            "timestamp": "2026-03-16T13:01:30Z",
            "data": {"status": status, "trace_id": trace_id},
        }
    )

    return events


def _pick_main_skill(discover_results: list[dict[str, Any]]) -> str:
    preferred = ["web.search-summary", "web.fetch-summary", "web.page-summary"]
    ranked_ids = [
        item.get("id")
        for item in discover_results
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    ]
    for skill_id in preferred:
        if skill_id in ranked_ids:
            return skill_id
    if ranked_ids:
        return ranked_ids[0]
    raise RuntimeError("No candidate main skill returned by skill.discover")


def _build_main_inputs(main_skill_id: str, prompt: str) -> dict[str, Any]:
    if main_skill_id == "web.search-summary":
        return {
            "query": (
                "oil price forecast next days brent wti drivers supply demand geopolitics "
                f"user_request: {prompt}"
            ),
            "limit": 5,
        }
    if main_skill_id == "web.fetch-summary":
        return {
            "url": "https://www.reuters.com/markets/commodities/",
            "max_length": 800,
        }
    if main_skill_id == "agent.plan-and-route":
        return {"objective": prompt}
    if main_skill_id == "agent.plan-from-objective":
        return {"objective": prompt}
    return {"input": prompt}


def _build_business_result(main_exec: dict[str, Any]) -> dict[str, Any]:
    outputs = (
        main_exec.get("outputs") if isinstance(main_exec.get("outputs"), dict) else {}
    )
    raw_summary = (
        outputs.get("summary") if isinstance(outputs.get("summary"), str) else ""
    )
    results = outputs.get("results") if isinstance(outputs.get("results"), list) else []

    text_corpus = f"{raw_summary} {' '.join(str(item) for item in results)}".lower()
    bullish_hits = sum(
        1
        for token in ("up", "rise", "higher", "bull", "rebound", "tight supply")
        if token in text_corpus
    )
    bearish_hits = sum(
        1
        for token in ("down", "fall", "lower", "bear", "surplus", "weak demand")
        if token in text_corpus
    )

    if bullish_hits > bearish_hits:
        thesis = "Sesgo alcista (probable suba)"
    elif bearish_hits > bullish_hits:
        thesis = "Sesgo bajista (probable baja)"
    else:
        thesis = "Sesgo neutral/mixto"

    evidence_snippets: list[str] = []
    for item in results[:3]:
        evidence_snippets.append(str(item)[:220])

    confidence_level = "media"
    if abs(bullish_hits - bearish_hits) >= 2:
        confidence_level = "media-alta"
    if raw_summary.strip() == "" and not results:
        confidence_level = "baja"

    return {
        "thesis": thesis,
        "confidence_level": confidence_level,
        "signals": {
            "bullish_hits": bullish_hits,
            "bearish_hits": bearish_hits,
            "sources_count": len(results),
        },
        "narrative_summary": raw_summary,
        "evidence_snippets": evidence_snippets,
        "disclaimer": "Estimacion heuristica basada en skills web; no constituye recomendacion financiera.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Demo MCP autonomous flow: primary problem solving + agent.trace sidecar."
    )
    parser.add_argument(
        "--runtime-root", type=Path, default=Path(__file__).resolve().parent.parent
    )
    parser.add_argument("--registry-root", type=Path, default=None)
    parser.add_argument("--host-root", type=Path, default=None)
    parser.add_argument("--prompt", type=str, default=DEFAULT_PROMPT)
    parser.add_argument("--target-ref", type=str, default=None)
    args = parser.parse_args()

    runtime_root = args.runtime_root.resolve()
    registry_root = (
        args.registry_root or (runtime_root.parent / "agent-skill-registry")
    ).resolve()
    host_root = (
        args.host_root or (runtime_root / "artifacts" / "trace-instance")
    ).resolve()

    env = dict(os.environ)
    modules_path = host_root / "modules"
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        f"{modules_path}{';' if existing_pythonpath else ''}{existing_pythonpath}"
    )

    target_ref = _select_target_ref(runtime_root, args.target_ref)

    first = _mcp_call(
        runtime_root=runtime_root,
        registry_root=registry_root,
        host_root=host_root,
        requests=[
            {"id": "1", "method": "tools/list"},
            {
                "id": "2",
                "method": "tools/call",
                "params": {
                    "name": "skill.discover",
                    "arguments": {
                        "intent": "Solve market question about oil direction with available web/agent skills",
                        "domain": "web",
                        "limit": 5,
                    },
                },
            },
            {
                "id": "3",
                "method": "tools/call",
                "params": {
                    "name": "skill.discover",
                    "arguments": {
                        "intent": "Trace operations and decisions during agent execution",
                        "domain": "agent",
                        "limit": 5,
                    },
                },
            },
        ],
        env=env,
    )

    tools = first.get("1", {}).get("result", {}).get("tools", [])
    tool_names = [t.get("name") for t in tools if isinstance(t, dict)]

    main_candidates = first.get("2", {}).get("result", {}).get("results", [])
    trace_candidates = first.get("3", {}).get("result", {}).get("results", [])

    main_skill_id = _pick_main_skill(
        main_candidates if isinstance(main_candidates, list) else []
    )
    trace_skill_id = "agent.trace"
    trace_found = any(
        isinstance(item, dict) and item.get("id") == trace_skill_id
        for item in (trace_candidates if isinstance(trace_candidates, list) else [])
    )
    if not trace_found:
        raise RuntimeError(
            "agent.trace was not returned by trace discovery in this run"
        )

    second = _mcp_call(
        runtime_root=runtime_root,
        registry_root=registry_root,
        host_root=host_root,
        requests=[
            {
                "id": "4",
                "method": "tools/call",
                "params": {
                    "name": "skill.execute",
                    "arguments": {
                        "skill_id": main_skill_id,
                        "inputs": _build_main_inputs(main_skill_id, args.prompt),
                        "include_trace": True,
                    },
                },
            }
        ],
        env=env,
    )

    main_exec = second.get("4", {}).get("result", {})
    if not isinstance(main_exec, dict) or main_exec.get("status") != "completed":
        raise RuntimeError(
            "Primary job did not complete successfully. "
            f"payload={json.dumps(second.get('4', {}), ensure_ascii=False)}"
        )

    trace_events = _build_trace_events(main_exec, args.prompt, main_skill_id)

    third = _mcp_call(
        runtime_root=runtime_root,
        registry_root=registry_root,
        host_root=host_root,
        requests=[
            {
                "id": "5",
                "method": "tools/call",
                "params": {
                    "name": "skill.attach",
                    "arguments": {
                        "skill_id": trace_skill_id,
                        "target_type": "output",
                        "target_ref": target_ref,
                        "include_trace": True,
                        "inputs": {
                            "goal": f"Trace sidecar for: {args.prompt}",
                            "context": {
                                "pattern": "dual-job",
                                "main_skill": main_skill_id,
                                "trace_mode": "attached-sidecar",
                            },
                            "events": trace_events,
                            "trace_state": {},
                            "trace_session_id": "session-mcp-dual-job",
                            "state_mode": "incremental",
                            "mode": "standard",
                            "output_views": [
                                "decision_graph",
                                "assumptions",
                                "alternative_paths",
                                "summary",
                            ],
                            "thresholds": {"max_risk_flags": 2, "min_confidence": 0.4},
                        },
                    },
                },
            }
        ],
        env=env,
    )

    trace_attach = third.get("5", {}).get("result", {})
    if not isinstance(trace_attach, dict):
        raise RuntimeError("Trace attach did not return a valid payload")

    trace_exec = (
        trace_attach.get("execution", {}) if isinstance(trace_attach, dict) else {}
    )
    trace_outputs = (
        trace_exec.get("outputs", {}) if isinstance(trace_exec, dict) else {}
    )

    summary = {
        "autonomous_prompt": args.prompt,
        "tools_available": tool_names,
        "main_job": {
            "selected_skill": main_skill_id,
            "status": main_exec.get("status"),
            "trace_id": main_exec.get("trace_id"),
            "output_keys": sorted(list(main_exec.get("outputs", {}).keys()))
            if isinstance(main_exec.get("outputs"), dict)
            else [],
        },
        "business_result": _build_business_result(main_exec),
        "trace_job": {
            "selected_skill": trace_skill_id,
            "status": trace_exec.get("status"),
            "trace_id": trace_exec.get("trace_id"),
            "analysis_source": (
                trace_outputs.get("updated_trace_state", {}).get("analysis_source")
                if isinstance(trace_outputs.get("updated_trace_state"), dict)
                else None
            ),
            "control_status": trace_outputs.get("control_status"),
            "confidence": trace_outputs.get("confidence"),
            "risk_flags": trace_outputs.get("risk_flags"),
            "alerts": trace_outputs.get("alerts"),
            "target_ref": target_ref,
        },
    }

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

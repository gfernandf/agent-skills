#!/usr/bin/env python3
"""
Pilot stability verifier for the canonical cognitive capability decision.input.route.

What this script measures:
- Baseline behavior (forced python binding)
- OpenAPI behavior (forced OpenAPI binding)
- Fallback behavior (forced failing primary -> expected python fallback)
- Alias diagnostics (agent.input.route) for compatibility vs canonical taxonomy

Outputs:
- Console summary
- Optional JSON report (default: artifacts/decision_input_route_stability_report.json)
"""

from __future__ import annotations

import argparse
import json
import math
import os
import tempfile
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
REGISTRY_ROOT = ROOT.parent / "agent-skill-registry"
DEFAULT_REPORT = ROOT / "artifacts" / "decision_input_route_stability_report.json"

import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from customer_facing.neutral_api import NeutralRuntimeAPI  # noqa: E402
from runtime.binding_registry import BindingRegistry  # noqa: E402
from runtime.capability_loader import YamlCapabilityLoader  # noqa: E402


CANONICAL_ID = "decision.input.route"
ALIAS_ID = "agent.input.route"


@dataclass(frozen=True)
class CaseSpec:
    case_id: str
    description: str
    inputs: dict[str, Any]
    expected_route_signals: tuple[str, ...]
    hard_agent_restriction: bool = False


@dataclass(frozen=True)
class LaneSpec:
    lane_id: str
    description: str
    mode: str


TEST_CASES: tuple[CaseSpec, ...] = (
    CaseSpec(
        case_id="summary",
        description="Summary-oriented request",
        inputs={
            "query": "Summarize this quarterly earnings report",
            "agents": ["summarizer", "analyst", "translator"],
            "routing_strategy": "keyword",
        },
        expected_route_signals=("summar", "resum", "reasoning.content.summarize"),
    ),
    CaseSpec(
        case_id="risk",
        description="Risk/security-oriented request",
        inputs={
            "query": "Assess security risk for this deployment",
            "agents": ["risk_assessor", "summarizer"],
            "routing_strategy": "keyword",
        },
        expected_route_signals=("risk", "security", "evaluation.risk.score"),
    ),
    CaseSpec(
        case_id="plan",
        description="Planning-oriented request",
        inputs={
            "query": "Create a 3-step rollout plan",
            "agents": ["planner", "analyst"],
            "routing_strategy": "keyword",
        },
        expected_route_signals=("plan", "roadmap", "reasoning.plan.generate"),
    ),
    CaseSpec(
        case_id="restricted_single_agent",
        description="Restricted to one available handler",
        inputs={
            "query": "Help me with this",
            "agents": ["analyst"],
            "routing_strategy": "keyword",
        },
        expected_route_signals=("analyst",),
        hard_agent_restriction=True,
    ),
    CaseSpec(
        case_id="no_agents",
        description="No agents list provided",
        inputs={
            "query": "Summarize and classify this text",
            "routing_strategy": "semantic",
        },
        expected_route_signals=("summar", "class", "reasoning."),
    ),
    CaseSpec(
        case_id="spanish_summary",
        description="Spanish summary request",
        inputs={
            "query": "Necesito un resumen ejecutivo breve",
            "agents": ["resumidor", "analista"],
            "routing_strategy": "keyword",
        },
        expected_route_signals=("resum", "summar", "reasoning.content.summarize"),
    ),
    CaseSpec(
        case_id="noisy_text",
        description="Noisy punctuation/casing",
        inputs={
            "query": "  !!! SuMmArIzE -- THIS... now???   ",
            "agents": ["summarizer", "analyst"],
            "routing_strategy": "keyword",
        },
        expected_route_signals=("summar", "resum", "reasoning.content.summarize"),
    ),
    CaseSpec(
        case_id="strategy_semantic",
        description="Same intent with semantic hint",
        inputs={
            "query": "Summarize this quarterly earnings report",
            "agents": ["summarizer", "analyst", "translator"],
            "routing_strategy": "semantic",
        },
        expected_route_signals=("summar", "resum", "reasoning.content.summarize"),
    ),
)


LANES: tuple[LaneSpec, ...] = (
    LaneSpec(
        lane_id="baseline_forced",
        description="Force python baseline binding",
        mode="baseline",
    ),
    LaneSpec(
        lane_id="openapi_forced",
        description="Force OpenAPI binding",
        mode="openapi",
    ),
    LaneSpec(
        lane_id="fallback_induced",
        description="Force failing local OpenAPI primary and verify fallback",
        mode="fallback",
    ),
)


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except Exception:
        return str(path)


def _normalize_route(route: Any) -> str:
    if not isinstance(route, str):
        return ""
    return route.strip().lower()


def _route_entropy(routes: list[str]) -> float:
    if not routes:
        return 0.0
    counts = Counter(routes)
    total = float(sum(counts.values()))
    entropy = 0.0
    for c in counts.values():
        p = c / total
        entropy -= p * math.log2(p)
    return round(entropy, 6)


def _resolve_capability_id() -> str:
    loader = YamlCapabilityLoader(REGISTRY_ROOT)
    all_caps = loader.get_all_capabilities()
    if CANONICAL_ID in all_caps:
        return CANONICAL_ID
    if ALIAS_ID in all_caps:
        return ALIAS_ID
    raise RuntimeError(
        f"Neither canonical nor alias capability exists: {CANONICAL_ID}, {ALIAS_ID}"
    )


def _get_bindings(capability_id: str) -> dict[str, str | None]:
    registry = BindingRegistry(repo_root=ROOT, host_root=ROOT)
    bindings = registry.get_bindings_for_capability(capability_id)
    by_id = {b.id: b for b in bindings}

    python_id = None
    openapi_id = None

    preferred_python = [
        "python_decision_input_route",
        "python_agent_route",
    ]
    preferred_openapi = [
        "openapi_decision_input_route_openai_chat",
        "openapi_agent_route_mock",
    ]

    for bid in preferred_python:
        b = by_id.get(bid)
        if b is not None and b.protocol == "pythoncall":
            python_id = bid
            break
    if python_id is None:
        for b in bindings:
            if b.protocol == "pythoncall":
                python_id = b.id
                break

    for bid in preferred_openapi:
        b = by_id.get(bid)
        if b is not None and b.protocol == "openapi":
            openapi_id = bid
            break
    if openapi_id is None:
        for b in bindings:
            if b.protocol == "openapi":
                openapi_id = b.id
                break

    return {
        "python": python_id,
        "openapi": openapi_id,
    }


def _write_active_binding(host_root: Path, capability_id: str, binding_id: str) -> None:
    agent_dir = host_root / ".agent-skills"
    agent_dir.mkdir(parents=True, exist_ok=True)
    payload = {capability_id: binding_id}
    (agent_dir / "active_bindings.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _write_failing_openapi_override(
    host_root: Path,
    *,
    capability_id: str,
    fallback_binding_id: str,
) -> str:
    agent_dir = host_root / ".agent-skills"
    agent_dir.mkdir(parents=True, exist_ok=True)

    failing_binding_id = "local_decision_input_route_failing"
    failing_service_id = "local_failing_route_openapi"

    (agent_dir / "services.yaml").write_text(
        "\n".join(
            [
                "services:",
                f"  {failing_service_id}:",
                "    kind: openapi",
                "    base_url: http://127.0.0.1:1",
                "    metadata:",
                "      timeout_seconds: 0.2",
                "",
            ]
        ),
        encoding="utf-8",
    )

    local_binding_dir = agent_dir / "bindings" / "local" / capability_id
    local_binding_dir.mkdir(parents=True, exist_ok=True)

    (local_binding_dir / "failing_route.yaml").write_text(
        "\n".join(
            [
                f"id: {failing_binding_id}",
                f"capability: {capability_id}",
                f"service: {failing_service_id}",
                "protocol: openapi",
                "operation: route",
                "request:",
                "  query: input.query",
                "  agents: input.agents",
                "  routing_strategy: input.routing_strategy",
                "response:",
                "  route: response.route",
                "  confidence: response.confidence",
                "metadata:",
                "  method: POST",
                "  response_mode: json",
                "  timeout_seconds: 0.2",
                f"  fallback_binding_id: {fallback_binding_id}",
                "",
            ]
        ),
        encoding="utf-8",
    )

    _write_active_binding(host_root, capability_id, failing_binding_id)
    return failing_binding_id


def _execute_once(host_root: Path, capability_id: str, inputs: dict[str, Any]) -> dict[str, Any]:
    api = NeutralRuntimeAPI(
        registry_root=REGISTRY_ROOT,
        runtime_root=ROOT,
        host_root=host_root,
    )
    return api.execute_capability(capability_id, inputs)


def _validate_result(
    *,
    lane: LaneSpec,
    case: CaseSpec,
    result: dict[str, Any],
    expected_primary_binding: str | None,
) -> dict[str, Any]:
    issue_records: list[dict[str, str]] = []

    error = result.get("error") if isinstance(result, dict) else None
    outputs = result.get("outputs") if isinstance(result, dict) else None
    meta = result.get("meta") if isinstance(result, dict) else None

    final_binding = None
    fallback_used = None
    if isinstance(meta, dict):
        final_binding = meta.get("binding_id")
        fallback_used = meta.get("fallback_used")

    if isinstance(error, dict):
        message = str(error.get("message", "execution error"))
        category = "integration_or_binding"
        low = message.lower()
        if "binding" in low and "not found" in low:
            category = "selection_or_fallback"
        if "capability" in low and "not found" in low:
            category = "contract_or_taxonomy"
        issue_records.append(
            {
                "severity": "high",
                "category": category,
                "reason": message,
            }
        )
        return {
            "ok": False,
            "invariants_pass": False,
            "semantic_pass": False,
            "route": "",
            "confidence": None,
            "final_binding": final_binding,
            "fallback_used": fallback_used,
            "issues": issue_records,
        }

    if not isinstance(outputs, dict):
        issue_records.append(
            {
                "severity": "high",
                "category": "integration_or_binding",
                "reason": "outputs payload is not a dict",
            }
        )
        return {
            "ok": False,
            "invariants_pass": False,
            "semantic_pass": False,
            "route": "",
            "confidence": None,
            "final_binding": final_binding,
            "fallback_used": fallback_used,
            "issues": issue_records,
        }

    route = outputs.get("route")
    confidence = outputs.get("confidence")
    route_norm = _normalize_route(route)

    invariants_pass = True
    if not route_norm:
        invariants_pass = False
        issue_records.append(
            {
                "severity": "high",
                "category": "contract_or_taxonomy",
                "reason": "missing required output 'route'",
            }
        )

    if confidence is not None:
        if not isinstance(confidence, (int, float)):
            invariants_pass = False
            issue_records.append(
                {
                    "severity": "high",
                    "category": "contract_or_taxonomy",
                    "reason": "confidence exists but is not numeric",
                }
            )
        elif float(confidence) < 0.0 or float(confidence) > 1.0:
            invariants_pass = False
            issue_records.append(
                {
                    "severity": "high",
                    "category": "contract_or_taxonomy",
                    "reason": "confidence outside [0,1]",
                }
            )

    agents = case.inputs.get("agents")
    if case.hard_agent_restriction and isinstance(agents, list) and len(agents) == 1:
        only_agent = str(agents[0]).strip().lower()
        if route_norm != only_agent:
            issue_records.append(
                {
                    "severity": "medium",
                    "category": (
                        "baseline_implementation"
                        if lane.mode == "baseline"
                        else "integration_or_binding"
                    ),
                    "reason": "single-agent restriction not respected",
                }
            )

    semantic_pass = True
    if case.expected_route_signals:
        semantic_pass = any(token in route_norm for token in case.expected_route_signals)
        if not semantic_pass:
            issue_records.append(
                {
                    "severity": "medium",
                    "category": (
                        "baseline_implementation"
                        if lane.mode == "baseline"
                        else "integration_or_binding"
                    ),
                    "reason": "route does not match expected semantic signals",
                }
            )

    if expected_primary_binding is not None and final_binding != expected_primary_binding:
        category = "selection_or_fallback"
        attempts = meta.get("attempts") if isinstance(meta, dict) else None
        if isinstance(attempts, list) and attempts:
            first = attempts[0]
            if isinstance(first, dict) and first.get("status") == "failed":
                err_type = str(first.get("error_type", ""))
                if err_type in {
                    "ResponseMappingError",
                    "RequestBuildError",
                    "OpenAPIInvocationError",
                }:
                    category = "integration_or_binding"

        # Binding mismatch can be caused by a real fallback policy event or by
        # an integration failure that forced fallback.
        issue_records.append(
            {
                "severity": "medium",
                "category": category,
                "reason": (
                    f"final binding '{final_binding}' differs from expected primary "
                    f"'{expected_primary_binding}'"
                ),
            }
        )

    return {
        "ok": invariants_pass,
        "invariants_pass": invariants_pass,
        "semantic_pass": semantic_pass,
        "route": route_norm,
        "confidence": confidence,
        "final_binding": final_binding,
        "fallback_used": fallback_used,
        "issues": issue_records,
    }


def _make_host_root() -> tempfile.TemporaryDirectory[str]:
    return tempfile.TemporaryDirectory(prefix="decision-input-route-stability-")


def _run_lane(
    *,
    lane: LaneSpec,
    capability_id: str,
    python_binding_id: str | None,
    openapi_binding_id: str | None,
    repetitions: int,
) -> dict[str, Any]:
    runs: list[dict[str, Any]] = []

    if lane.mode == "baseline" and python_binding_id is None:
        return {
            "lane_id": lane.lane_id,
            "description": lane.description,
            "status": "skipped",
            "reason": "no python binding found",
            "runs": [],
        }

    if lane.mode == "openapi" and openapi_binding_id is None:
        return {
            "lane_id": lane.lane_id,
            "description": lane.description,
            "status": "skipped",
            "reason": "no openapi binding found",
            "runs": [],
        }

    with _make_host_root() as temp_dir:
        host_root = Path(temp_dir)

        expected_primary_binding: str | None = None
        if lane.mode == "baseline":
            expected_primary_binding = python_binding_id
            _write_active_binding(host_root, capability_id, python_binding_id)
        elif lane.mode == "openapi":
            expected_primary_binding = openapi_binding_id
            _write_active_binding(host_root, capability_id, openapi_binding_id)
        elif lane.mode == "fallback":
            if python_binding_id is None:
                return {
                    "lane_id": lane.lane_id,
                    "description": lane.description,
                    "status": "skipped",
                    "reason": "fallback lane requires python binding",
                    "runs": [],
                }
            expected_primary_binding = "local_decision_input_route_failing"
            _write_failing_openapi_override(
                host_root,
                capability_id=capability_id,
                fallback_binding_id=python_binding_id,
            )

        for case in TEST_CASES:
            for idx in range(repetitions):
                result = _execute_once(host_root, capability_id, case.inputs)
                eval_info = _validate_result(
                    lane=lane,
                    case=case,
                    result=result,
                    expected_primary_binding=expected_primary_binding,
                )

                runs.append(
                    {
                        "case_id": case.case_id,
                        "iteration": idx + 1,
                        "inputs": case.inputs,
                        "result": result,
                        "evaluation": eval_info,
                    }
                )

    return {
        "lane_id": lane.lane_id,
        "description": lane.description,
        "status": "ok",
        "runs": runs,
    }


def _summarize_lane(lane_result: dict[str, Any]) -> dict[str, Any]:
    runs = lane_result.get("runs")
    if lane_result.get("status") != "ok" or not isinstance(runs, list):
        return {
            "lane_id": lane_result.get("lane_id"),
            "status": lane_result.get("status"),
            "reason": lane_result.get("reason"),
        }

    routes: list[str] = []
    issues: list[dict[str, str]] = []
    invariant_pass = 0
    semantic_pass = 0
    fallback_true = 0
    case_totals: dict[str, int] = {}
    case_invariants: dict[str, int] = {}
    case_semantics: dict[str, int] = {}
    case_issue_categories: dict[str, Counter] = {}

    for run in runs:
        ev = run.get("evaluation") if isinstance(run, dict) else None
        if not isinstance(ev, dict):
            continue
        route = ev.get("route")
        if isinstance(route, str) and route:
            routes.append(route)
        if ev.get("invariants_pass") is True:
            invariant_pass += 1
        if ev.get("semantic_pass") is True:
            semantic_pass += 1
        if ev.get("fallback_used") is True:
            fallback_true += 1

        case_id = run.get("case_id") if isinstance(run, dict) else None
        if isinstance(case_id, str) and case_id:
            case_totals[case_id] = case_totals.get(case_id, 0) + 1
            if ev.get("invariants_pass") is True:
                case_invariants[case_id] = case_invariants.get(case_id, 0) + 1
            if ev.get("semantic_pass") is True:
                case_semantics[case_id] = case_semantics.get(case_id, 0) + 1

        issue_list = ev.get("issues")
        if isinstance(issue_list, list):
            for item in issue_list:
                if isinstance(item, dict):
                    issues.append(item)
                    if isinstance(case_id, str) and case_id:
                        category = item.get("category")
                        if isinstance(category, str) and category:
                            bucket = case_issue_categories.setdefault(
                                case_id, Counter()
                            )
                            bucket[category] += 1

    lane_total = len(runs)
    route_counts = Counter(routes)
    dominant_route = route_counts.most_common(1)[0][0] if route_counts else None

    issue_category_counts = Counter()
    for issue in issues:
        category = issue.get("category")
        if isinstance(category, str):
            issue_category_counts[category] += 1

    per_case: dict[str, Any] = {}
    for case_id, case_runs in case_totals.items():
        inv = case_invariants.get(case_id, 0)
        sem = case_semantics.get(case_id, 0)
        issue_dist = case_issue_categories.get(case_id, Counter())
        per_case[case_id] = {
            "runs": case_runs,
            "invariant_pass_rate": round(inv / case_runs, 4)
            if case_runs
            else 0.0,
            "semantic_pass_rate": round(sem / case_runs, 4)
            if case_runs
            else 0.0,
            "issue_categories": dict(issue_dist),
        }

    return {
        "lane_id": lane_result.get("lane_id"),
        "status": "ok",
        "runs": lane_total,
        "invariant_pass_rate": round(invariant_pass / lane_total, 4)
        if lane_total
        else 0.0,
        "semantic_pass_rate": round(semantic_pass / lane_total, 4)
        if lane_total
        else 0.0,
        "fallback_activation_rate": round(fallback_true / lane_total, 4)
        if lane_total
        else 0.0,
        "dominant_route": dominant_route,
        "route_entropy": _route_entropy(routes),
        "route_distribution": dict(route_counts),
        "issue_categories": dict(issue_category_counts),
        "per_case": per_case,
    }


def _run_alias_diagnostics(capability_id: str, repetitions: int) -> dict[str, Any]:
    loader = YamlCapabilityLoader(REGISTRY_ROOT)
    all_caps = loader.get_all_capabilities()

    if ALIAS_ID not in all_caps or capability_id == ALIAS_ID:
        return {
            "status": "skipped",
            "reason": "alias capability not available as separate contract",
        }

    bindings = _get_bindings(ALIAS_ID)
    python_alias = bindings.get("python")
    if not isinstance(python_alias, str) or not python_alias:
        return {
            "status": "skipped",
            "reason": "no python alias binding found",
        }

    with _make_host_root() as temp_dir:
        host_root = Path(temp_dir)
        _write_active_binding(host_root, ALIAS_ID, python_alias)
        runs: list[dict[str, Any]] = []
        for idx in range(repetitions):
            case = TEST_CASES[0]
            result = _execute_once(host_root, ALIAS_ID, case.inputs)
            outputs = result.get("outputs") if isinstance(result, dict) else None
            route = outputs.get("route") if isinstance(outputs, dict) else None
            confidence = outputs.get("confidence") if isinstance(outputs, dict) else None
            runs.append(
                {
                    "iteration": idx + 1,
                    "route": route,
                    "confidence": confidence,
                    "meta": result.get("meta") if isinstance(result, dict) else None,
                    "error": result.get("error") if isinstance(result, dict) else None,
                }
            )

    return {
        "status": "ok",
        "alias_capability_id": ALIAS_ID,
        "binding_id": python_alias,
        "runs": runs,
    }


def _build_overall_assessment(lane_summaries: list[dict[str, Any]]) -> dict[str, Any]:
    summary_by_lane = {item.get("lane_id"): item for item in lane_summaries}

    baseline = summary_by_lane.get("baseline_forced", {})
    openapi = summary_by_lane.get("openapi_forced", {})
    fallback = summary_by_lane.get("fallback_induced", {})

    findings: list[dict[str, Any]] = []

    if baseline.get("status") == "ok":
        if baseline.get("invariant_pass_rate", 0.0) < 1.0:
            findings.append(
                {
                    "severity": "high",
                    "category": "baseline_implementation",
                    "reason": "baseline invariant pass rate below 1.0",
                    "evidence": baseline,
                }
            )
        if baseline.get("semantic_pass_rate", 0.0) < 0.8:
            findings.append(
                {
                    "severity": "medium",
                    "category": "baseline_implementation",
                    "reason": "baseline semantic pass rate below 0.8",
                    "evidence": baseline,
                }
            )

    if openapi.get("status") == "ok":
        if openapi.get("invariant_pass_rate", 0.0) < 0.95:
            findings.append(
                {
                    "severity": "high",
                    "category": "integration_or_binding",
                    "reason": "openapi invariant pass rate below 0.95",
                    "evidence": openapi,
                }
            )
        if openapi.get("fallback_activation_rate", 0.0) > 0.2:
            findings.append(
                {
                    "severity": "medium",
                    "category": "selection_or_fallback",
                    "reason": "openapi lane often falls back to non-primary binding",
                    "evidence": openapi,
                }
            )

    if fallback.get("status") == "ok":
        if fallback.get("fallback_activation_rate", 0.0) < 0.95:
            findings.append(
                {
                    "severity": "high",
                    "category": "selection_or_fallback",
                    "reason": "forced fallback lane did not consistently activate fallback",
                    "evidence": fallback,
                }
            )

    stable = len(findings) == 0
    return {
        "stable": stable,
        "findings": findings,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Pilot stability verifier for decision.input.route"
    )
    parser.add_argument(
        "--repetitions",
        type=int,
        default=10,
        help="Repetitions per case per lane (default: 10)",
    )
    parser.add_argument(
        "--report-file",
        type=Path,
        default=DEFAULT_REPORT,
        help=(
            "Path to write JSON report "
            f"(default: {_safe_rel(DEFAULT_REPORT)})"
        ),
    )
    parser.add_argument(
        "--skip-openapi",
        action="store_true",
        help="Skip the forced OpenAPI lane",
    )
    parser.add_argument(
        "--skip-fallback",
        action="store_true",
        help="Skip the induced-fallback lane",
    )
    parser.add_argument(
        "--skip-alias-diagnostics",
        action="store_true",
        help="Skip compatibility alias diagnostics",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.repetitions < 1:
        raise SystemExit("--repetitions must be >= 1")

    capability_id = _resolve_capability_id()
    bindings = _get_bindings(capability_id)

    python_binding_id = bindings.get("python")
    openapi_binding_id = bindings.get("openapi")

    selected_lanes = []
    for lane in LANES:
        if lane.mode == "openapi" and args.skip_openapi:
            continue
        if lane.mode == "fallback" and args.skip_fallback:
            continue
        selected_lanes.append(lane)

    lane_results: list[dict[str, Any]] = []
    for lane in selected_lanes:
        lane_results.append(
            _run_lane(
                lane=lane,
                capability_id=capability_id,
                python_binding_id=python_binding_id
                if isinstance(python_binding_id, str)
                else None,
                openapi_binding_id=openapi_binding_id
                if isinstance(openapi_binding_id, str)
                else None,
                repetitions=args.repetitions,
            )
        )

    lane_summaries = [_summarize_lane(item) for item in lane_results]

    alias_diag = None
    if not args.skip_alias_diagnostics:
        alias_diag = _run_alias_diagnostics(capability_id, repetitions=min(5, args.repetitions))

    overall = _build_overall_assessment(lane_summaries)

    report = {
        "generated_at": _iso_now(),
        "capability_id": capability_id,
        "canonical_id": CANONICAL_ID,
        "alias_id": ALIAS_ID,
        "environment": {
            "openai_api_key_present": bool(os.getenv("OPENAI_API_KEY")),
        },
        "bindings": {
            "python": python_binding_id,
            "openapi": openapi_binding_id,
        },
        "repetitions": args.repetitions,
        "cases": [
            {
                "case_id": c.case_id,
                "description": c.description,
                "inputs": c.inputs,
                "expected_route_signals": c.expected_route_signals,
                "hard_agent_restriction": c.hard_agent_restriction,
            }
            for c in TEST_CASES
        ],
        "lane_summaries": lane_summaries,
        "lane_results": lane_results,
        "alias_diagnostics": alias_diag,
        "overall_assessment": overall,
    }

    args.report_file.parent.mkdir(parents=True, exist_ok=True)
    args.report_file.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print("Decision-input-route stability report generated")
    print(f"  capability: {capability_id}")
    print(f"  report: {_safe_rel(args.report_file)}")

    print("\nLane summary:")
    for item in lane_summaries:
        lane_id = item.get("lane_id")
        status = item.get("status")
        if status != "ok":
            print(f"  - {lane_id}: {status} ({item.get('reason')})")
            continue
        print(
            "  - "
            f"{lane_id}: inv={item.get('invariant_pass_rate')} "
            f"sem={item.get('semantic_pass_rate')} "
            f"fallback={item.get('fallback_activation_rate')} "
            f"entropy={item.get('route_entropy')}"
        )

    stable = bool(overall.get("stable"))
    if stable:
        print("\nOverall: STABLE")
        return 0

    print("\nOverall: UNSTABLE")
    findings = overall.get("findings")
    if isinstance(findings, list):
        for finding in findings:
            if not isinstance(finding, dict):
                continue
            print(
                f"  - [{finding.get('severity')}] "
                f"{finding.get('category')}: {finding.get('reason')}"
            )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""
Generic stability verifier for cognitive-layer capabilities.

This extends the decision.input.route pilot approach to a matrix runner:
- discovers cognitive capabilities from registry contracts
- generates test cases from examples + schema-driven synthetic input
- executes baseline/openapi/fallback lanes in isolated host roots
- computes invariant + semantic pass rates and issue categories
- writes per-capability and consolidated reports

Notes:
- OpenAPI lane is local-only by default to avoid accidental external spend.
- Remote OpenAPI can be enabled with --allow-remote-openapi.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import tempfile
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
REGISTRY_ROOT = ROOT.parent / "agent-skill-registry"
DEFAULT_OUT_DIR = ROOT / "artifacts" / "cognitive_stability"
DEFAULT_MATRIX_FILE = ROOT / "artifacts" / "cognitive_stability_matrix.json"
DEFAULT_CASEPACK_FILE = ROOT / "tooling" / "stability_casepacks" / "cognitive_pure_casepacks.yaml"

import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from customer_facing.neutral_api import NeutralRuntimeAPI  # noqa: E402
from runtime.binding_registry import BindingRegistry  # noqa: E402


REMOTE_HOST_HINTS = (
    "openai.com",
    "anthropic.com",
    "googleapis.com",
    "azure.com",
    "mistral.ai",
    "cohere.ai",
)


@dataclass(frozen=True)
class CaseSpec:
    case_id: str
    description: str
    inputs: dict[str, Any]
    expected_signals: dict[str, tuple[str, ...]]


@dataclass(frozen=True)
class LaneSpec:
    lane_id: str
    description: str
    mode: str


LANES: tuple[LaneSpec, ...] = (
    LaneSpec("baseline_forced", "Force python baseline binding", "baseline"),
    LaneSpec("openapi_forced", "Force OpenAPI primary binding", "openapi"),
    LaneSpec("fallback_induced", "Force failing OpenAPI primary and verify fallback", "fallback"),
)


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except Exception:
        return str(path)


def _safe_slug(capability_id: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]", "_", capability_id)


def _normalize_str(value: Any) -> str:
    return value.strip().lower() if isinstance(value, str) else ""


def _route_entropy(values: list[str]) -> float:
    if not values:
        return 0.0
    counts = Counter(values)
    total = float(sum(counts.values()))
    entropy = 0.0
    for c in counts.values():
        p = c / total
        entropy -= p * math.log2(p)
    return round(entropy, 6)


def _read_capability_docs() -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    caps_dir = REGISTRY_ROOT / "capabilities"
    for path in sorted(caps_dir.glob("*.yaml")):
        if path.name == "_index.yaml":
            continue
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8-sig"))
        except Exception:
            continue
        if not isinstance(raw, dict):
            continue
        cap_id = raw.get("id")
        if not isinstance(cap_id, str) or not cap_id:
            continue
        metadata = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
        layer = metadata.get("layer")
        if layer != "cognitive":
            continue
        docs.append(raw)
    return docs


def _load_casepacks(casepack_file: Path) -> dict[str, list[CaseSpec]]:
    if not casepack_file.exists():
        return {}
    try:
        raw = yaml.safe_load(casepack_file.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}
    if not isinstance(raw, dict):
        return {}

    packs: dict[str, list[CaseSpec]] = {}
    for cap_id, cases_raw in raw.items():
        if not isinstance(cap_id, str) or not isinstance(cases_raw, list):
            continue
        cases: list[CaseSpec] = []
        for idx, item in enumerate(cases_raw, start=1):
            if not isinstance(item, dict):
                continue
            inputs = item.get("inputs")
            if not isinstance(inputs, dict) or not inputs:
                continue
            expected_raw = item.get("expected_signals")
            expected: dict[str, tuple[str, ...]] = {}
            if isinstance(expected_raw, dict):
                for out_name, tokens in expected_raw.items():
                    if not isinstance(out_name, str):
                        continue
                    if isinstance(tokens, list):
                        clean = tuple(str(t).strip().lower() for t in tokens if str(t).strip())
                    elif isinstance(tokens, str) and tokens.strip():
                        clean = (tokens.strip().lower(),)
                    else:
                        clean = ()
                    if clean:
                        expected[out_name] = clean

            case_id = item.get("case_id")
            if not isinstance(case_id, str) or not case_id:
                case_id = f"pack_case_{idx}"
            description = item.get("description")
            if not isinstance(description, str) or not description:
                description = "Casepack-provided scenario"
            cases.append(
                CaseSpec(
                    case_id=case_id,
                    description=description,
                    inputs=inputs,
                    expected_signals=expected,
                )
            )
        if cases:
            packs[cap_id] = cases
    return packs


def _default_value(field_name: str, field_type: str) -> Any:
    name = field_name.lower()
    ftype = field_type.lower()

    if ftype == "string":
        if "query" in name:
            return "Summarize key points and identify risks"
        if "text" in name or "content" in name:
            return "This is a sample input text with multiple ideas to process."
        if "strategy" in name:
            return "keyword"
        if "language" in name:
            return "en"
        return f"sample_{field_name}"
    if ftype in {"integer", "int"}:
        return 3
    if ftype in {"number", "float", "double"}:
        return 0.5
    if ftype in {"boolean", "bool"}:
        return True
    if ftype == "array":
        if "agent" in name:
            return ["summarizer", "analyst"]
        if "dimension" in name:
            return ["toxicity", "bias"]
        return ["item_a", "item_b"]
    if ftype == "object":
        if name in {"output", "record", "payload"}:
            return {"text": "sample object payload"}
        return {"value": "sample"}
    return f"sample_{field_name}"


def _required_inputs(raw_capability: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    inputs = raw_capability.get("inputs")
    if not isinstance(inputs, dict):
        return out

    for name, spec in inputs.items():
        if not isinstance(name, str) or not isinstance(spec, dict):
            continue
        if spec.get("required") is True:
            ftype = str(spec.get("type", "string"))
            out[name] = _default_value(name, ftype)

    if not out:
        for name, spec in inputs.items():
            if not isinstance(name, str) or not isinstance(spec, dict):
                continue
            ftype = str(spec.get("type", "string"))
            out[name] = _default_value(name, ftype)
            break

    return out


def _signals_from_example_outputs(example: dict[str, Any]) -> dict[str, tuple[str, ...]]:
    outputs = example.get("outputs")
    if not isinstance(outputs, dict):
        return {}

    signals: dict[str, tuple[str, ...]] = {}
    for out_name, expected in outputs.items():
        if not isinstance(out_name, str):
            continue
        if isinstance(expected, str):
            tokens = [t for t in re.split(r"\W+", expected.lower()) if len(t) >= 4]
            if tokens:
                signals[out_name] = tuple(tokens[:4])
        elif isinstance(expected, (int, float, bool)):
            # scalar expectations are already type-checked by invariants
            continue
    return signals


def _extract_examples(raw_capability: dict[str, Any]) -> list[dict[str, Any]]:
    metadata = raw_capability.get("metadata")
    if not isinstance(metadata, dict):
        return []
    examples = metadata.get("examples")
    if not isinstance(examples, list):
        return []
    return [e for e in examples if isinstance(e, dict)]


def _build_cases(raw_capability: dict[str, Any], pack_override: list[CaseSpec] | None) -> list[CaseSpec]:
    if pack_override:
        return pack_override

    cap_id = str(raw_capability.get("id", "unknown"))
    required_inputs = _required_inputs(raw_capability)
    if not required_inputs:
        return []

    cases: list[CaseSpec] = []
    examples = _extract_examples(raw_capability)

    for idx, ex in enumerate(examples[:2], start=1):
        inputs = ex.get("inputs") if isinstance(ex.get("inputs"), dict) else None
        if not inputs:
            # Some contracts expose top-level fields in examples; extract matching input keys.
            raw_inputs = raw_capability.get("inputs")
            if isinstance(raw_inputs, dict):
                guessed = {k: ex.get(k) for k in raw_inputs.keys() if k in ex}
                inputs = guessed if guessed else None

        if not inputs:
            continue

        combined = dict(required_inputs)
        combined.update(inputs)
        cases.append(
            CaseSpec(
                case_id=f"example_{idx}",
                description="Example-derived case",
                inputs=combined,
                # Keep semantic checks opt-in via curated casepacks.
                # Contract examples are heterogeneous and often include idealized
                # text outputs that are not suitable as hard stability gates.
                expected_signals={},
            )
        )

    if not cases:
        cases.append(
            CaseSpec(
                case_id="synthetic_base",
                description="Schema-derived required-input case",
                inputs=required_inputs,
                expected_signals={},
            )
        )

    # Add one noisy variant for string robustness.
    noisy = dict(cases[0].inputs)
    changed = False
    for key, value in list(noisy.items()):
        if isinstance(value, str) and value:
            noisy[key] = f"  !! {value} ???  "
            changed = True
            break
    if changed:
        cases.append(
            CaseSpec(
                case_id="noisy_variant",
                description="Noisy punctuation/casing variant",
                inputs=noisy,
                expected_signals=cases[0].expected_signals,
            )
        )

    return cases


def _choose_bindings(registry: BindingRegistry, capability_id: str) -> dict[str, Any]:
    bindings = registry.get_bindings_for_capability(capability_id)
    python_binding = None
    openapi_binding = None

    for b in bindings:
        if b.protocol == "pythoncall" and python_binding is None:
            python_binding = b
        if b.protocol == "openapi" and openapi_binding is None:
            openapi_binding = b

    return {
        "python": python_binding,
        "openapi": openapi_binding,
    }


def _service_is_local_openapi(registry: BindingRegistry, service_id: str) -> bool:
    try:
        svc = registry.get_service(service_id)
    except Exception:
        return False
    base = (svc.base_url or "").lower()
    if not base:
        return False
    if "localhost" in base or "127.0.0.1" in base:
        return True
    if any(h in base for h in REMOTE_HOST_HINTS):
        return False
    return False


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
    input_keys: list[str],
    output_keys: list[str],
) -> str:
    agent_dir = host_root / ".agent-skills"
    agent_dir.mkdir(parents=True, exist_ok=True)

    failing_binding_id = f"local_{capability_id.replace('.', '_')}_failing"
    failing_service_id = f"local_{capability_id.replace('.', '_')}_failing_openapi"

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

    request_lines = ["request:"]
    for key in input_keys:
        request_lines.append(f"  {key}: input.{key}")

    response_lines = ["response:"]
    for key in output_keys:
        response_lines.append(f"  {key}: response.{key}")

    binding_lines = [
        f"id: {failing_binding_id}",
        f"capability: {capability_id}",
        f"service: {failing_service_id}",
        "protocol: openapi",
        "operation: run",
        *request_lines,
        *response_lines,
        "metadata:",
        "  method: POST",
        "  response_mode: json",
        "  timeout_seconds: 0.2",
        f"  fallback_binding_id: {fallback_binding_id}",
        "",
    ]

    (local_binding_dir / "failing_primary.yaml").write_text(
        "\n".join(binding_lines),
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


def _type_ok(expected_type: str, value: Any) -> bool:
    t = expected_type.lower()
    if t == "string":
        return isinstance(value, str)
    if t in {"integer", "int"}:
        return isinstance(value, int) and not isinstance(value, bool)
    if t in {"number", "float", "double"}:
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if t in {"boolean", "bool"}:
        return isinstance(value, bool)
    if t == "array":
        return isinstance(value, list)
    if t == "object":
        return isinstance(value, dict)
    return True


def _validate_result(
    *,
    lane: LaneSpec,
    case: CaseSpec,
    result: dict[str, Any],
    output_specs: dict[str, dict[str, Any]],
    expected_primary_binding: str | None,
) -> dict[str, Any]:
    issues: list[dict[str, str]] = []

    error = result.get("error") if isinstance(result, dict) else None
    outputs = result.get("outputs") if isinstance(result, dict) else None
    meta = result.get("meta") if isinstance(result, dict) else None

    final_binding = meta.get("binding_id") if isinstance(meta, dict) else None
    fallback_used = meta.get("fallback_used") if isinstance(meta, dict) else None

    if isinstance(error, dict):
        msg = str(error.get("message", "execution error"))
        category = "integration_or_binding"
        low = msg.lower()
        if "binding" in low and "not found" in low:
            category = "selection_or_fallback"
        if "capability" in low and "not found" in low:
            category = "contract_or_taxonomy"
        issues.append({"severity": "high", "category": category, "reason": msg})
        return {
            "invariants_pass": False,
            "semantic_pass": False,
            "route_like": "",
            "final_binding": final_binding,
            "fallback_used": fallback_used,
            "issues": issues,
        }

    if not isinstance(outputs, dict):
        issues.append(
            {
                "severity": "high",
                "category": "integration_or_binding",
                "reason": "outputs payload is not a dict",
            }
        )
        return {
            "invariants_pass": False,
            "semantic_pass": False,
            "route_like": "",
            "final_binding": final_binding,
            "fallback_used": fallback_used,
            "issues": issues,
        }

    invariants_pass = True

    for out_name, spec in output_specs.items():
        required = bool(spec.get("required"))
        ftype = str(spec.get("type", "string"))

        if required and out_name not in outputs:
            invariants_pass = False
            issues.append(
                {
                    "severity": "high",
                    "category": "contract_or_taxonomy",
                    "reason": f"missing required output '{out_name}'",
                }
            )
            continue

        if out_name in outputs and outputs[out_name] is not None:
            if not _type_ok(ftype, outputs[out_name]):
                invariants_pass = False
                issues.append(
                    {
                        "severity": "high",
                        "category": "contract_or_taxonomy",
                        "reason": f"output '{out_name}' has wrong type (expected {ftype})",
                    }
                )

            if ftype in {"number", "integer", "float", "double"}:
                low_name = out_name.lower()
                if any(k in low_name for k in ("score", "confidence", "risk")):
                    try:
                        val = float(outputs[out_name])
                    except Exception:
                        val = None
                    if val is None or val < 0.0 or val > 1.0:
                        invariants_pass = False
                        issues.append(
                            {
                                "severity": "high",
                                "category": "contract_or_taxonomy",
                                "reason": f"output '{out_name}' outside [0,1]",
                            }
                        )

    semantic_pass = True
    if case.expected_signals:
        for out_name, tokens in case.expected_signals.items():
            val = outputs.get(out_name)
            if not isinstance(val, str):
                semantic_pass = False
                issues.append(
                    {
                        "severity": "medium",
                        "category": (
                            "baseline_implementation"
                            if lane.mode == "baseline"
                            else "integration_or_binding"
                        ),
                        "reason": f"semantic check output '{out_name}' not string",
                    }
                )
                continue
            norm = val.lower()
            if not any(tok in norm for tok in tokens):
                semantic_pass = False
                issues.append(
                    {
                        "severity": "medium",
                        "category": (
                            "baseline_implementation"
                            if lane.mode == "baseline"
                            else "integration_or_binding"
                        ),
                        "reason": f"output '{out_name}' missing expected semantic signals",
                    }
                )
    else:
        semantic_pass = invariants_pass

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
        issues.append(
            {
                "severity": "medium",
                "category": category,
                "reason": (
                    f"final binding '{final_binding}' differs from expected primary "
                    f"'{expected_primary_binding}'"
                ),
            }
        )

    route_like = ""
    for candidate in ("route", "decision", "summary", "result", "status"):
        value = outputs.get(candidate)
        if isinstance(value, str) and value.strip():
            route_like = value.strip().lower()
            break

    return {
        "invariants_pass": invariants_pass,
        "semantic_pass": semantic_pass,
        "route_like": route_like,
        "final_binding": final_binding,
        "fallback_used": fallback_used,
        "issues": issues,
    }


def _run_lane(
    *,
    lane: LaneSpec,
    capability_id: str,
    cases: list[CaseSpec],
    output_specs: dict[str, dict[str, Any]],
    input_keys: list[str],
    python_binding_id: str | None,
    openapi_binding_id: str | None,
) -> dict[str, Any]:
    if lane.mode == "baseline" and python_binding_id is None:
        return {
            "lane_id": lane.lane_id,
            "status": "skipped",
            "reason": "no python binding found",
            "runs": [],
        }

    if lane.mode == "openapi" and openapi_binding_id is None:
        return {
            "lane_id": lane.lane_id,
            "status": "skipped",
            "reason": "no openapi binding found",
            "runs": [],
        }

    if lane.mode == "fallback" and python_binding_id is None:
        return {
            "lane_id": lane.lane_id,
            "status": "skipped",
            "reason": "fallback lane requires python binding",
            "runs": [],
        }

    runs: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="cognitive-stability-") as temp_dir:
        host_root = Path(temp_dir)
        expected_primary_binding: str | None = None

        if lane.mode == "baseline":
            expected_primary_binding = python_binding_id
            _write_active_binding(host_root, capability_id, python_binding_id)
        elif lane.mode == "openapi":
            expected_primary_binding = openapi_binding_id
            _write_active_binding(host_root, capability_id, openapi_binding_id)
        else:
            output_keys = [k for k, spec in output_specs.items() if spec.get("required")]
            if not output_keys:
                output_keys = list(output_specs.keys())[:2] or ["status"]
            expected_primary_binding = _write_failing_openapi_override(
                host_root,
                capability_id=capability_id,
                fallback_binding_id=python_binding_id,
                input_keys=input_keys,
                output_keys=output_keys,
            )

        for case in cases:
            result = _execute_once(host_root, capability_id, case.inputs)
            evaluation = _validate_result(
                lane=lane,
                case=case,
                result=result,
                output_specs=output_specs,
                expected_primary_binding=expected_primary_binding,
            )
            runs.append(
                {
                    "case_id": case.case_id,
                    "inputs": case.inputs,
                    "result": result,
                    "evaluation": evaluation,
                }
            )

    return {
        "lane_id": lane.lane_id,
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

    route_like: list[str] = []
    issues: list[dict[str, str]] = []
    inv_pass = 0
    sem_pass = 0
    fb_true = 0

    for run in runs:
        ev = run.get("evaluation") if isinstance(run, dict) else None
        if not isinstance(ev, dict):
            continue
        if ev.get("invariants_pass") is True:
            inv_pass += 1
        if ev.get("semantic_pass") is True:
            sem_pass += 1
        if ev.get("fallback_used") is True:
            fb_true += 1
        rv = ev.get("route_like")
        if isinstance(rv, str) and rv:
            route_like.append(rv)
        issue_list = ev.get("issues")
        if isinstance(issue_list, list):
            for it in issue_list:
                if isinstance(it, dict):
                    issues.append(it)

    total = len(runs)
    cat_counts = Counter()
    for item in issues:
        cat = item.get("category")
        if isinstance(cat, str):
            cat_counts[cat] += 1

    return {
        "lane_id": lane_result.get("lane_id"),
        "status": "ok",
        "runs": total,
        "invariant_pass_rate": round(inv_pass / total, 4) if total else 0.0,
        "semantic_pass_rate": round(sem_pass / total, 4) if total else 0.0,
        "fallback_activation_rate": round(fb_true / total, 4) if total else 0.0,
        "route_entropy": _route_entropy(route_like),
        "issue_categories": dict(cat_counts),
    }


def _assess_capability(lane_summaries: list[dict[str, Any]]) -> dict[str, Any]:
    by_id = {s.get("lane_id"): s for s in lane_summaries}
    baseline = by_id.get("baseline_forced", {})
    openapi = by_id.get("openapi_forced", {})
    fallback = by_id.get("fallback_induced", {})

    findings: list[dict[str, Any]] = []
    skips: list[dict[str, str]] = []

    for lane in (baseline, openapi, fallback):
        if lane.get("status") == "skipped":
            skips.append({"lane_id": str(lane.get("lane_id")), "reason": str(lane.get("reason"))})

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
        "skips": skips,
    }


def _run_for_capability(
    *,
    raw_capability: dict[str, Any],
    casepacks: dict[str, list[CaseSpec]],
    registry: BindingRegistry,
    allow_remote_openapi: bool,
) -> dict[str, Any]:
    capability_id = str(raw_capability.get("id"))
    inputs_spec = raw_capability.get("inputs") if isinstance(raw_capability.get("inputs"), dict) else {}
    outputs_spec = raw_capability.get("outputs") if isinstance(raw_capability.get("outputs"), dict) else {}

    input_keys = [k for k in inputs_spec.keys() if isinstance(k, str)]
    normalized_output_specs: dict[str, dict[str, Any]] = {}
    for key, spec in outputs_spec.items():
        if isinstance(key, str) and isinstance(spec, dict):
            normalized_output_specs[key] = {
                "required": bool(spec.get("required")),
                "type": str(spec.get("type", "string")),
            }

    cases = _build_cases(raw_capability, casepacks.get(capability_id))
    if not cases:
        return {
            "capability_id": capability_id,
            "status": "skipped",
            "reason": "could not build any input cases",
        }

    bindings = _choose_bindings(registry, capability_id)
    python_binding = bindings.get("python")
    openapi_binding = bindings.get("openapi")

    python_binding_id = python_binding.id if python_binding is not None else None
    openapi_binding_id = openapi_binding.id if openapi_binding is not None else None

    openapi_policy_skip_reason = None
    if openapi_binding is not None and not allow_remote_openapi:
        if not _service_is_local_openapi(registry, openapi_binding.service_id):
            openapi_policy_skip_reason = "openapi lane disabled for remote service (use --allow-remote-openapi)"
            openapi_binding_id = None

    lane_results: list[dict[str, Any]] = []
    for lane in LANES:
        if lane.mode == "openapi" and openapi_policy_skip_reason is not None:
            lane_results.append(
                {
                    "lane_id": lane.lane_id,
                    "status": "skipped",
                    "reason": openapi_policy_skip_reason,
                    "runs": [],
                }
            )
            continue
        lane_results.append(
            _run_lane(
                lane=lane,
                capability_id=capability_id,
                cases=cases,
                output_specs=normalized_output_specs,
                input_keys=input_keys,
                python_binding_id=python_binding_id,
                openapi_binding_id=openapi_binding_id,
            )
        )

    lane_summaries = [_summarize_lane(l) for l in lane_results]
    overall = _assess_capability(lane_summaries)

    return {
        "capability_id": capability_id,
        "status": "ok",
        "bindings": {
            "python": python_binding.id if python_binding is not None else None,
            "openapi": openapi_binding.id if openapi_binding is not None else None,
            "openapi_service": openapi_binding.service_id if openapi_binding is not None else None,
        },
        "cases": [
            {
                "case_id": c.case_id,
                "description": c.description,
                "inputs": c.inputs,
                "expected_signals": c.expected_signals,
            }
            for c in cases
        ],
        "lane_summaries": lane_summaries,
        "lane_results": lane_results,
        "overall_assessment": overall,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify stability matrix for all cognitive-layer capabilities"
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=DEFAULT_OUT_DIR,
        help=f"Per-capability report directory (default: {_safe_rel(DEFAULT_OUT_DIR)})",
    )
    parser.add_argument(
        "--matrix-file",
        type=Path,
        default=DEFAULT_MATRIX_FILE,
        help=f"Consolidated matrix file (default: {_safe_rel(DEFAULT_MATRIX_FILE)})",
    )
    parser.add_argument(
        "--casepack-file",
        type=Path,
        default=DEFAULT_CASEPACK_FILE,
        help=f"Optional casepack YAML (default: {_safe_rel(DEFAULT_CASEPACK_FILE)})",
    )
    parser.add_argument(
        "--capability-prefix",
        type=str,
        default="",
        help="Optional prefix filter (e.g. reasoning. or decision.)",
    )
    parser.add_argument(
        "--max-capabilities",
        type=int,
        default=0,
        help="Optional max capabilities to run after filtering (0 = no limit)",
    )
    parser.add_argument(
        "--allow-remote-openapi",
        action="store_true",
        help="Run OpenAPI lane even when service appears remote/external",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    raw_caps = _read_capability_docs()
    if args.capability_prefix:
        raw_caps = [c for c in raw_caps if str(c.get("id", "")).startswith(args.capability_prefix)]
    raw_caps = sorted(raw_caps, key=lambda c: str(c.get("id", "")))

    if args.max_capabilities and args.max_capabilities > 0:
        raw_caps = raw_caps[: args.max_capabilities]

    casepacks = _load_casepacks(args.casepack_file)
    registry = BindingRegistry(repo_root=ROOT, host_root=ROOT)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    args.matrix_file.parent.mkdir(parents=True, exist_ok=True)

    capability_reports: list[dict[str, Any]] = []

    for cap in raw_caps:
        report = _run_for_capability(
            raw_capability=cap,
            casepacks=casepacks,
            registry=registry,
            allow_remote_openapi=args.allow_remote_openapi,
        )
        capability_reports.append(report)

        if report.get("status") == "ok":
            out_path = args.out_dir / f"{_safe_slug(str(report['capability_id']))}.json"
            out_path.write_text(
                json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

    stable = 0
    unstable = 0
    skipped = 0
    category_counts: Counter[str] = Counter()

    for report in capability_reports:
        if report.get("status") != "ok":
            skipped += 1
            continue
        overall = report.get("overall_assessment") if isinstance(report.get("overall_assessment"), dict) else {}
        findings = overall.get("findings") if isinstance(overall.get("findings"), list) else []
        if overall.get("stable") is True:
            stable += 1
        else:
            unstable += 1
        for finding in findings:
            if isinstance(finding, dict):
                cat = finding.get("category")
                if isinstance(cat, str):
                    category_counts[cat] += 1

    matrix = {
        "generated_at": _iso_now(),
        "environment": {
            "openai_api_key_present": bool(os.getenv("OPENAI_API_KEY")),
            "allow_remote_openapi": bool(args.allow_remote_openapi),
        },
        "scope": {
            "layer": "cognitive",
            "capability_prefix": args.capability_prefix or None,
            "capabilities_considered": len(raw_caps),
        },
        "summary": {
            "stable": stable,
            "unstable": unstable,
            "skipped": skipped,
            "finding_categories": dict(category_counts),
        },
        "capability_reports": [
            {
                "capability_id": r.get("capability_id"),
                "status": r.get("status"),
                "overall_assessment": r.get("overall_assessment"),
                "bindings": r.get("bindings"),
            }
            for r in capability_reports
        ],
    }

    args.matrix_file.write_text(
        json.dumps(matrix, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print("Cognitive stability matrix generated")
    print(f"  capabilities: {len(raw_caps)}")
    print(f"  stable: {stable}")
    print(f"  unstable: {unstable}")
    print(f"  skipped: {skipped}")
    print(f"  matrix: {_safe_rel(args.matrix_file)}")
    print(f"  per-capability dir: {_safe_rel(args.out_dir)}")

    return 0 if unstable == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

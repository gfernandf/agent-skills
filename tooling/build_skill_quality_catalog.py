#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Allow importing runtime modules from repository root.
sys.path.insert(0, str(Path(__file__).parent.parent))

from runtime.binding_registry import BindingRegistry
from runtime.capability_loader import YamlCapabilityLoader


STATE_RANK = {
    "draft": 0,
    "validated": 1,
    "lab-verified": 2,
    "trusted": 3,
    "recommended": 4,
}


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, sort_keys=False)
        f.write("\n")


def _load_optional_skill_map(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}

    raw = _read_json(path)
    if not isinstance(raw, dict):
        raise ValueError(f"Optional evidence file '{path}' must contain an object.")

    skills = raw.get("skills", raw)
    if not isinstance(skills, dict):
        raise ValueError(
            f"Optional evidence file '{path}' must contain a 'skills' object or direct skill map."
        )

    normalized: dict[str, dict[str, Any]] = {}
    for skill_id, value in skills.items():
        if isinstance(skill_id, str) and skill_id and isinstance(value, dict):
            normalized[skill_id] = value

    return normalized


def _clamp(value: float, minimum: float = 0.0, maximum: float = 100.0) -> float:
    return max(minimum, min(maximum, value))


def _score_latency(p95_duration_ms: float | None) -> float:
    if p95_duration_ms is None:
        return 60.0
    if p95_duration_ms <= 3000:
        return 100.0
    if p95_duration_ms <= 8000:
        return 75.0
    if p95_duration_ms <= 15000:
        return 55.0
    return 35.0


def _score_rating(rating_avg: float | None, rating_count: int) -> float:
    # Bayesian smoothing avoids unstable ratings in early adoption.
    prior = 3.8
    prior_weight = 10

    if rating_avg is None:
        smoothed = prior
    else:
        smoothed = ((rating_avg * rating_count) + (prior * prior_weight)) / (
            rating_count + prior_weight
        )

    return _clamp(((smoothed - 1.0) / 4.0) * 100.0)


def _compute_executability(
    *,
    skills_catalog: list[dict[str, Any]],
    capability_loader: YamlCapabilityLoader,
    binding_registry: BindingRegistry,
) -> dict[str, bool]:
    result: dict[str, bool] = {}

    for skill in skills_catalog:
        if not isinstance(skill, dict):
            continue

        skill_id = skill.get("id")
        if not isinstance(skill_id, str) or not skill_id:
            continue

        uses_capabilities = skill.get("uses_capabilities", [])
        if not isinstance(uses_capabilities, list):
            uses_capabilities = []

        executable = True
        for capability_id in uses_capabilities:
            if not isinstance(capability_id, str) or not capability_id:
                executable = False
                break

            try:
                capability_loader.get_capability(capability_id)
            except Exception:
                executable = False
                break

            if not binding_registry.get_bindings_for_capability(capability_id):
                executable = False
                break

        result[skill_id] = executable

    return result


def _conformance_profile_score(profile: str) -> float:
    if profile == "strict":
        return 100.0
    if profile == "standard":
        return 75.0
    if profile == "experimental":
        return 45.0
    return 60.0


def _resolve_binding_profile(binding: Any) -> str:
    metadata = binding.metadata if hasattr(binding, "metadata") else {}
    if isinstance(metadata, dict):
        value = metadata.get("conformance_profile")
        if isinstance(value, str) and value:
            return value
    return "standard"


def _compute_skill_conformance_metrics(
    skill: dict[str, Any], binding_registry: BindingRegistry
) -> dict[str, Any]:
    uses_capabilities = skill.get("uses_capabilities", [])
    if not isinstance(uses_capabilities, list):
        uses_capabilities = []

    profiles: list[str] = []

    for capability_id in uses_capabilities:
        if not isinstance(capability_id, str) or not capability_id:
            continue

        default_binding_id = binding_registry.get_official_default_binding_id(
            capability_id
        )
        if not isinstance(default_binding_id, str) or not default_binding_id:
            continue

        try:
            binding = binding_registry.get_binding(default_binding_id)
        except Exception:
            continue

        profiles.append(_resolve_binding_profile(binding))

    if not profiles:
        return {
            "conformance_score": 60.0,
            "profile_counts": {"strict": 0, "standard": 0, "experimental": 0},
            "lowest_profile": None,
        }

    counts = {
        "strict": profiles.count("strict"),
        "standard": profiles.count("standard"),
        "experimental": profiles.count("experimental"),
    }
    score = sum(_conformance_profile_score(profile) for profile in profiles) / len(
        profiles
    )

    lowest = "strict"
    if counts["experimental"] > 0:
        lowest = "experimental"
    elif counts["standard"] > 0:
        lowest = "standard"

    return {
        "conformance_score": round(score, 2),
        "profile_counts": counts,
        "lowest_profile": lowest,
    }


def _metadata_list_size(metadata: Any, key: str) -> int:
    if not isinstance(metadata, dict):
        return 0
    value = metadata.get(key)
    return len(value) if isinstance(value, list) else 0


def _compute_readiness_score(
    skill: dict[str, Any],
    executable: bool,
    lab: dict[str, Any],
    conformance_metrics: dict[str, Any],
) -> tuple[float, list[str]]:
    score = 0.0
    flags: list[str] = []

    if executable:
        score += 35.0
    else:
        flags.append("not_executable")

    if skill.get("channel") == "official":
        score += 15.0
    else:
        flags.append("non_official_channel")

    metadata = skill.get("metadata", {})
    if _metadata_list_size(metadata, "use_cases") > 0:
        score += 10.0
    else:
        flags.append("missing_use_cases")

    if _metadata_list_size(metadata, "examples") > 0:
        score += 10.0
    else:
        flags.append("missing_examples")

    if _metadata_list_size(metadata, "tags") > 0:
        score += 5.0
    else:
        flags.append("missing_tags")

    status = metadata.get("status") if isinstance(metadata, dict) else None
    if isinstance(status, str) and status.lower() in {
        "stable",
        "validated",
        "production",
    }:
        score += 5.0

    if lab.get("contract_passed") is True:
        score += 8.0
    else:
        flags.append("lab_contract_not_passed")

    if lab.get("smoke_passed") is True:
        score += 6.0
    else:
        flags.append("lab_smoke_not_passed")

    if lab.get("review_passed") is True:
        score += 4.0
    else:
        flags.append("lab_review_not_passed")

    if lab.get("control_points_passed") is True:
        score += 2.0
    else:
        flags.append("lab_control_points_not_passed")

    manual = lab.get("manual_score")
    if isinstance(manual, (int, float)):
        score = _clamp(float(manual))
        flags.append("manual_readiness_override")

    conformance_score = float(conformance_metrics.get("conformance_score", 60.0))
    conformance_penalty = max(0.0, (70.0 - conformance_score) * 0.25)
    if conformance_penalty > 0:
        flags.append("low_conformance_default_path")

    return _clamp(score - conformance_penalty), flags


def _compute_field_metrics(
    usage: dict[str, Any], feedback: dict[str, Any]
) -> dict[str, Any]:
    executions = int(usage.get("executions_30d", 0) or 0)
    successes = int(usage.get("successes_30d", 0) or 0)
    timeouts = int(usage.get("timeouts_30d", 0) or 0)
    p50 = usage.get("p50_duration_ms")
    p95 = usage.get("p95_duration_ms")

    rating_avg_raw = feedback.get("rating_avg")
    rating_count = int(feedback.get("rating_count", 0) or 0)
    reports = int(feedback.get("reports_30d", 0) or 0)
    severe_reports = int(feedback.get("severe_reports_30d", 0) or 0)

    rating_avg = (
        float(rating_avg_raw) if isinstance(rating_avg_raw, (int, float)) else None
    )

    success_rate = (successes / executions) if executions > 0 else None
    timeout_rate = (timeouts / executions) if executions > 0 else None

    reliability_score = (success_rate * 100.0) if success_rate is not None else 0.0
    if timeout_rate is not None:
        reliability_score = _clamp(reliability_score - (timeout_rate * 20.0))

    latency_score = _score_latency(
        float(p95) if isinstance(p95, (int, float)) else None
    )
    rating_score = _score_rating(rating_avg, rating_count)

    reports_penalty = min(40.0, (float(reports) * 2.0) + (float(severe_reports) * 8.0))
    safety_score = _clamp(100.0 - reports_penalty)

    if executions <= 0:
        field_score = 0.0
    else:
        field_score = _clamp(
            (0.50 * reliability_score)
            + (0.20 * latency_score)
            + (0.20 * rating_score)
            + (0.10 * safety_score)
        )

    return {
        "executions_30d": executions,
        "successes_30d": successes,
        "success_rate_30d": round(success_rate, 4)
        if success_rate is not None
        else None,
        "timeouts_30d": timeouts,
        "timeout_rate_30d": round(timeout_rate, 4)
        if timeout_rate is not None
        else None,
        "p50_duration_ms": p50 if isinstance(p50, (int, float)) else None,
        "p95_duration_ms": p95 if isinstance(p95, (int, float)) else None,
        "rating_avg": round(rating_avg, 3) if rating_avg is not None else None,
        "rating_count": rating_count,
        "reports_30d": reports,
        "severe_reports_30d": severe_reports,
        "field_score": round(field_score, 2),
    }


def _compute_overall_score(
    readiness_score: float, field_score: float, executions_30d: int
) -> float:
    if executions_30d < 20:
        return round(readiness_score, 2)
    if executions_30d < 50:
        return round((0.80 * readiness_score) + (0.20 * field_score), 2)
    return round((0.40 * readiness_score) + (0.60 * field_score), 2)


def _resolve_state(
    *,
    readiness_score: float,
    overall_score: float,
    metrics: dict[str, Any],
) -> str:
    executions = metrics["executions_30d"]
    success_rate = metrics["success_rate_30d"] or 0.0
    severe_reports = metrics["severe_reports_30d"]
    rating_avg = metrics["rating_avg"]
    rating_count = metrics["rating_count"]

    if readiness_score >= 75.0:
        state = "lab-verified"
    elif readiness_score >= 50.0:
        state = "validated"
    else:
        state = "draft"

    if (
        executions >= 50
        and success_rate >= 0.95
        and severe_reports == 0
        and overall_score >= 80.0
        and readiness_score >= 60.0
    ):
        state = "trusted"

    if (
        state == "trusted"
        and executions >= 200
        and rating_count >= 20
        and (rating_avg or 0.0) >= 4.2
        and overall_score >= 88.0
    ):
        state = "recommended"

    return state


def _resolve_evidence_source(executions_30d: int) -> str:
    if executions_30d <= 0:
        return "internal-evidence"
    if executions_30d < 50:
        return "mixed-evidence"
    return "field-evidence"


def build_skill_quality_catalog(
    *,
    registry_root: Path,
    runtime_root: Path,
    host_root: Path,
    lab_file: Path,
    usage_file: Path,
    feedback_file: Path,
    output_file: Path,
) -> dict[str, Any]:
    skills_catalog_path = registry_root / "catalog" / "skills.json"
    if not skills_catalog_path.exists():
        raise FileNotFoundError(
            f"Missing '{skills_catalog_path}'. Run registry catalog generation first."
        )

    skills = _read_json(skills_catalog_path)
    if not isinstance(skills, list):
        raise ValueError("catalog/skills.json must contain a list.")

    capability_loader = YamlCapabilityLoader(registry_root)
    binding_registry = BindingRegistry(runtime_root, host_root)

    executability = _compute_executability(
        skills_catalog=skills,
        capability_loader=capability_loader,
        binding_registry=binding_registry,
    )

    lab_map = _load_optional_skill_map(lab_file)
    usage_map = _load_optional_skill_map(usage_file)
    feedback_map = _load_optional_skill_map(feedback_file)

    entries: list[dict[str, Any]] = []

    for skill in skills:
        if not isinstance(skill, dict):
            continue

        skill_id = skill.get("id")
        if not isinstance(skill_id, str) or not skill_id:
            continue

        executable = executability.get(skill_id, False)
        lab = lab_map.get(skill_id, {})
        usage = usage_map.get(skill_id, {})
        feedback = feedback_map.get(skill_id, {})
        conformance_metrics = _compute_skill_conformance_metrics(
            skill, binding_registry
        )

        readiness_score, readiness_flags = _compute_readiness_score(
            skill,
            executable,
            lab,
            conformance_metrics,
        )
        field_metrics = _compute_field_metrics(usage, feedback)
        overall_score = _compute_overall_score(
            readiness_score=readiness_score,
            field_score=field_metrics["field_score"],
            executions_30d=field_metrics["executions_30d"],
        )
        lifecycle_state = _resolve_state(
            readiness_score=readiness_score,
            overall_score=overall_score,
            metrics=field_metrics,
        )

        entry = {
            "skill_id": skill_id,
            "channel": skill.get("channel"),
            "domain": skill.get("domain"),
            "readiness_score": round(readiness_score, 2),
            "field_score": field_metrics["field_score"],
            "overall_score": overall_score,
            "lifecycle_state": lifecycle_state,
            "evidence_source": _resolve_evidence_source(
                field_metrics["executions_30d"]
            ),
            "metrics": field_metrics,
            "conformance": conformance_metrics,
            "flags": sorted(set(readiness_flags)),
        }

        entries.append(entry)

    entries.sort(
        key=lambda x: (
            -STATE_RANK.get(str(x.get("lifecycle_state")), -1),
            -float(x.get("overall_score", 0.0)),
            str(x.get("skill_id", "")),
        )
    )

    summary = {
        "total_skills": len(entries),
        "by_state": {
            state: sum(1 for e in entries if e.get("lifecycle_state") == state)
            for state in [
                "draft",
                "validated",
                "lab-verified",
                "trusted",
                "recommended",
            ]
        },
        "avg_scores": {
            "readiness": round(
                sum(e["readiness_score"] for e in entries) / len(entries), 2
            )
            if entries
            else 0.0,
            "field": round(sum(e["field_score"] for e in entries) / len(entries), 2)
            if entries
            else 0.0,
            "overall": round(sum(e["overall_score"] for e in entries) / len(entries), 2)
            if entries
            else 0.0,
        },
    }

    output = {
        "version": "1.0",
        "inputs": {
            "lab_validation": str(lab_file.as_posix()),
            "usage": str(usage_file.as_posix()),
            "feedback": str(feedback_file.as_posix()),
        },
        "summary": summary,
        "skills": entries,
    }

    _write_json(output_file, output)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(prog="build_skill_quality_catalog")
    parser.add_argument("--registry-root", type=Path, default=None)
    parser.add_argument("--runtime-root", type=Path, default=None)
    parser.add_argument("--host-root", type=Path, default=None)
    parser.add_argument(
        "--lab-file",
        type=Path,
        default=Path("artifacts") / "skill_lab_validation.json",
    )
    parser.add_argument(
        "--usage-file",
        type=Path,
        default=Path("artifacts") / "skill_usage_30d.json",
    )
    parser.add_argument(
        "--feedback-file",
        type=Path,
        default=Path("artifacts") / "skill_feedback_30d.json",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("artifacts") / "skill_quality.json",
    )
    args = parser.parse_args()

    runtime_root = args.runtime_root or Path.cwd()
    registry_root = args.registry_root or (runtime_root.parent / "agent-skill-registry")
    host_root = args.host_root or runtime_root

    try:
        result = build_skill_quality_catalog(
            registry_root=registry_root,
            runtime_root=runtime_root,
            host_root=host_root,
            lab_file=args.lab_file,
            usage_file=args.usage_file,
            feedback_file=args.feedback_file,
            output_file=args.out,
        )
    except Exception as e:
        print(f"SKILL QUALITY GENERATION FAILED: {e}")
        return 1

    print("SKILL QUALITY CATALOG GENERATED")
    print(f"Skills: {result['summary']['total_skills']}")
    print("By state:")
    for state, count in result["summary"]["by_state"].items():
        print(f"- {state}: {count}")
    print(f"Written: {args.out.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

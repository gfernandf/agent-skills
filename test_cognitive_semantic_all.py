from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sdk.embedded import execute_capability, reset
from test_cognitive_capabilities_e2e import (
    _build_inputs,
    _load_active_cognitive_capabilities,
)


REPORT_PATH = (
    Path(__file__).resolve().parent / "artifacts" / "cognitive_semantic_all_report.json"
)


@dataclass
class SemanticResult:
    capability_id: str
    status: str
    errors: list[str]
    input_payload: dict[str, Any]
    output_payload: dict[str, Any] | None
    exception_type: str | None = None
    exception_message: str | None = None


_PLACEHOLDER_TOKENS = (
    "fallback",
    "valor de prueba",
    "output (",
    "python_fallback",
)


def _is_placeholder_text(value: str) -> bool:
    low = value.lower()
    return any(token in low for token in _PLACEHOLDER_TOKENS)


def _validate_number_semantics(
    field_name: str, value: float, errors: list[str]
) -> None:
    name = field_name.lower()
    if any(
        tok in name
        for tok in ("score", "confidence", "similarity", "ratio", "coverage")
    ):
        if not (0.0 <= value <= 1.0):
            errors.append(
                f"numeric range violation for {field_name}: expected [0,1], got {value}"
            )


def _validate_array_semantics(
    field_name: str, value: list[Any], output_payload: dict[str, Any], errors: list[str]
) -> None:
    allow_empty_arrays = {
        "conflicts",
        "unresolved_bindings",
        "rejected_options",
        "rejected_strategies",
    }

    if len(value) == 0 and field_name not in allow_empty_arrays:
        errors.append(f"empty array for {field_name}")
        return
    if len(value) == 0:
        return

    name = field_name.lower()

    if name.startswith("ranked_"):
        for idx, item in enumerate(value, start=1):
            if isinstance(item, dict):
                rank = item.get("rank")
                if not isinstance(rank, int) or rank < 1:
                    errors.append(f"invalid rank in {field_name} at index {idx}")

    if field_name == "scored_options":
        for item in value:
            if not isinstance(item, dict):
                errors.append("scored_options items must be objects")
                continue
            if not isinstance(item.get("option_id"), str):
                errors.append("scored_options item missing option_id")
            score = item.get("overall_score")
            if not isinstance(score, (int, float)):
                errors.append("scored_options item missing numeric overall_score")
            elif not (0.0 <= float(score) <= 1.0):
                errors.append(f"scored_options overall_score out of range: {score}")

    if field_name == "source_scores":
        for item in value:
            if not isinstance(item, dict):
                errors.append("source_scores items must be objects")
                continue
            overall = item.get("overall")
            if not isinstance(overall, (int, float)):
                errors.append("source_scores item missing overall")
            elif not (0.0 <= float(overall) <= 1.0):
                errors.append(f"source_scores overall out of range: {overall}")

    if field_name == "prioritized_uncertainties":
        for item in value:
            if not isinstance(item, dict):
                errors.append("prioritized_uncertainties items must be objects")
                continue
            if not isinstance(item.get("uncertainty_id"), str):
                errors.append("prioritized_uncertainties item missing uncertainty_id")

    if field_name == "rejected_options" and "selected_option" in output_payload:
        selected = output_payload.get("selected_option")
        selected_id = selected.get("id") if isinstance(selected, dict) else None
        rejected_ids = {
            item.get("option")
            for item in value
            if isinstance(item, dict) and isinstance(item.get("option"), str)
        }
        if isinstance(selected_id, str) and selected_id in rejected_ids:
            errors.append("selected_option appears in rejected_options")


def _validate_object_semantics(
    field_name: str, value: dict[str, Any], errors: list[str]
) -> None:
    if not value:
        errors.append(f"empty object for {field_name}")
        return

    if field_name == "selected_option":
        if not isinstance(value.get("id"), str):
            errors.append("selected_option missing id")

    if field_name == "recommendation":
        if not isinstance(value.get("confidence"), (int, float)):
            errors.append("recommendation missing confidence")

    if field_name == "report":
        user_response = value.get("user_response")
        artifacts = value.get("artifacts")
        if not isinstance(user_response, str) or not user_response.strip():
            errors.append("report.user_response is empty")
        if not isinstance(artifacts, list) or not artifacts:
            errors.append("report.artifacts is empty")


def _validate_semantics(
    capability: dict[str, Any], output_payload: dict[str, Any]
) -> list[str]:
    outputs = capability.get("outputs") or {}
    errors: list[str] = []

    for field_name, spec in outputs.items():
        if not isinstance(spec, dict):
            continue
        if field_name not in output_payload:
            continue

        value = output_payload[field_name]
        expected_type = str(spec.get("type", "string"))
        required = bool(spec.get("required", False))

        if required and value in (None, "", [], {}):
            errors.append(f"required field has empty value: {field_name}")
            continue

        if expected_type == "string":
            if not isinstance(value, str):
                errors.append(f"type mismatch for {field_name}: expected string")
                continue
            enum_like_fields = (
                "level",
                "severity",
                "status",
                "sentiment",
                "freshness_hint",
            )
            min_len = (
                3
                if any(token in field_name.lower() for token in enum_like_fields)
                else 8
            )
            if len(value.strip()) < min_len:
                errors.append(f"string too short for {field_name}")
            if _is_placeholder_text(value):
                errors.append(f"placeholder text detected in {field_name}")

        elif expected_type == "number":
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                errors.append(f"type mismatch for {field_name}: expected number")
                continue
            _validate_number_semantics(field_name, float(value), errors)

        elif expected_type == "array":
            if not isinstance(value, list):
                errors.append(f"type mismatch for {field_name}: expected array")
                continue
            _validate_array_semantics(field_name, value, output_payload, errors)

        elif expected_type == "object":
            if not isinstance(value, dict):
                errors.append(f"type mismatch for {field_name}: expected object")
                continue
            _validate_object_semantics(field_name, value, errors)

        elif expected_type == "boolean":
            if not isinstance(value, bool):
                errors.append(f"type mismatch for {field_name}: expected boolean")

    if "embedding" in output_payload:
        emb = output_payload["embedding"]
        if not isinstance(emb, list) or len(emb) < 8:
            errors.append(
                "embedding quality issue: expected numeric vector with length >= 8"
            )
        else:
            if not all(isinstance(x, (int, float)) for x in emb):
                errors.append(
                    "embedding quality issue: vector contains non-numeric values"
                )

    capability_id = str(capability.get("id", ""))
    _validate_family_specific_semantics(capability_id, output_payload, errors)

    return errors


def _validate_family_specific_semantics(
    capability_id: str,
    output_payload: dict[str, Any],
    errors: list[str],
) -> None:
    if capability_id == "decision.option.justify":
        recommendation = output_payload.get("recommendation")
        alternatives = output_payload.get("alternatives_considered")
        if not isinstance(recommendation, str) or len(recommendation.strip()) < 12:
            errors.append("decision.option.justify recommendation lacks actionable detail")
        if not isinstance(alternatives, list) or not alternatives:
            errors.append("decision.option.justify requires non-empty alternatives_considered")

    if capability_id == "evaluation.plan.validate":
        vr = output_payload.get("validation_result")
        validation_errors = output_payload.get("validation_errors")
        validation_warnings = output_payload.get("validation_warnings")
        if not isinstance(vr, dict):
            errors.append("evaluation.plan.validate validation_result must be an object")
            return

        status = vr.get("status")
        if status not in {"passed", "failed"}:
            errors.append("evaluation.plan.validate validation_result.status must be passed|failed")

        if not isinstance(validation_errors, list):
            errors.append("evaluation.plan.validate validation_errors must be an array")
        if not isinstance(validation_warnings, list):
            errors.append("evaluation.plan.validate validation_warnings must be an array")

        # Validation should always provide at least one evaluative signal.
        if isinstance(validation_errors, list) and isinstance(validation_warnings, list):
            if len(validation_errors) + len(validation_warnings) == 0:
                errors.append("evaluation.plan.validate needs at least one validation signal")

    if capability_id == "reasoning.option.generate":
        options = output_payload.get("options")
        if not isinstance(options, list) or len(options) < 2:
            errors.append("reasoning.option.generate should produce at least two options")

    if capability_id == "reasoning.plan.generate":
        plan = output_payload.get("plan")
        if not isinstance(plan, dict):
            errors.append("reasoning.plan.generate plan must be an object")
            return
        steps = plan.get("steps")
        if not isinstance(steps, list) or not steps:
            errors.append("reasoning.plan.generate plan.steps must be non-empty")


def _run_semantic_all() -> list[SemanticResult]:
    capabilities = _load_active_cognitive_capabilities()
    results: list[SemanticResult] = []

    previous_openai_key = os.environ.pop("OPENAI_API_KEY", None)
    try:
        reset()
        for capability in capabilities:
            cap_id = str(capability.get("id"))
            payload = _build_inputs(capability)
            try:
                output = execute_capability(cap_id, payload)
                errors = _validate_semantics(capability, output)
                status = "passed" if not errors else "failed"
                results.append(
                    SemanticResult(
                        capability_id=cap_id,
                        status=status,
                        errors=errors,
                        input_payload=payload,
                        output_payload=output,
                    )
                )
            except Exception as exc:
                results.append(
                    SemanticResult(
                        capability_id=cap_id,
                        status="failed",
                        errors=[f"execution exception: {type(exc).__name__}: {exc}"],
                        input_payload=payload,
                        output_payload=None,
                        exception_type=type(exc).__name__,
                        exception_message=str(exc),
                    )
                )
    finally:
        if previous_openai_key is not None:
            os.environ["OPENAI_API_KEY"] = previous_openai_key
        reset()

    return results


def _write_report(results: list[SemanticResult]) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    failed = [r for r in results if r.status != "passed"]
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total": len(results),
        "passed": len(results) - len(failed),
        "failed": len(failed),
        "results": [
            {
                "capability_id": r.capability_id,
                "status": r.status,
                "errors": r.errors,
                "exception_type": r.exception_type,
                "exception_message": r.exception_message,
                "input": r.input_payload,
                "output": r.output_payload,
            }
            for r in results
        ],
    }
    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def test_all_cognitive_capabilities_semantic_quality() -> None:
    results = _run_semantic_all()
    _write_report(results)

    failures = [r for r in results if r.status != "passed"]
    if failures:
        first = ", ".join(r.capability_id for r in failures[:12])
        raise AssertionError(
            f"{len(failures)} cognitive capabilities failed semantic quality checks. "
            f"First failures: {first}. See {REPORT_PATH.as_posix()}"
        )

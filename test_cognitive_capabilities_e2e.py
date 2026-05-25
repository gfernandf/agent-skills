from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from sdk.embedded import execute_capability, reset


ROOT = Path(__file__).resolve().parent
REGISTRY_ROOT = ROOT.parent / "agent-skill-registry"
CAPABILITIES_DIR = REGISTRY_ROOT / "capabilities"
REPORT_PATH = ROOT / "artifacts" / "cognitive_e2e_contract_report.json"


@dataclass
class CapabilityRunResult:
    capability_id: str
    status: str
    errors: list[str]
    input_payload: dict[str, Any]
    output_payload: dict[str, Any] | None = None
    exception_type: str | None = None
    exception_message: str | None = None


def _load_active_cognitive_capabilities() -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []

    for path in sorted(CAPABILITIES_DIR.glob("*.yaml")):
        try:
            item = yaml.safe_load(path.read_text(encoding="utf-8"))
        except Exception:
            continue

        if not isinstance(item, dict):
            continue

        item.setdefault("file", path.as_posix())
        metadata = item.get("metadata") or {}
        if not isinstance(metadata, dict):
            metadata = {}
        status = metadata.get("status", item.get("status"))
        if metadata.get("layer") == "cognitive" and status != "deprecated":
            selected.append(item)

    selected.sort(key=lambda c: c.get("id", ""))
    return selected


def _default_string_for_field(field_name: str) -> str:
    name = field_name.lower()
    if "language" in name:
        return "es"
    if "goal" in name:
        return "Evaluar alternativas y decidir una estrategia de ejecucion."
    if "summary" in name:
        return "Resumen de prueba para validacion E2E."
    if "query" in name:
        return "analisis de opciones con riesgo y costo"
    if "context" in name:
        return "Contexto de prueba E2E con restricciones de tiempo y presupuesto."
    if "text" in name or "content" in name:
        return (
            "El equipo necesita decidir entre tres alternativas con datos incompletos "
            "y diferentes niveles de riesgo operativo."
        )
    if "request" in name:
        return "Necesito una recomendacion accionable con criterios y tradeoffs."
    if "option" in name:
        return "opcion-a"
    return f"valor de prueba para {field_name}"


def _default_number_for_field(field_name: str) -> float:
    name = field_name.lower()
    if "max" in name:
        return 3.0
    if "min" in name:
        return 1.0
    if "weight" in name:
        return 1.0
    if "score" in name:
        return 0.7
    if "timeout" in name:
        return 30.0
    return 1.0


def _default_array_for_field(field_name: str) -> list[Any]:
    name = field_name.lower()

    if "options" in name:
        return [
            {
                "id": "opt-1",
                "label": "Lanzar MVP",
                "description": "Lanzamiento incremental con validacion temprana.",
            },
            {
                "id": "opt-2",
                "label": "Lanzar completo",
                "description": "Salida al mercado con alcance completo.",
            },
        ]
    if "scores" in name:
        return [
            {"option_id": "opt-1", "overall_score": 0.72},
            {"option_id": "opt-2", "overall_score": 0.61},
        ]
    if "criteria" in name:
        return [
            {
                "name": "impacto",
                "description": "Valor de negocio esperado",
                "weight": 1.0,
            },
            {
                "name": "riesgo",
                "description": "Exposicion operativa",
                "weight": 1.0,
            },
        ]
    if "fields" in name:
        return [
            {
                "name": "goal",
                "type": "string",
                "required": True,
                "description": "Objetivo principal de la solicitud",
            },
            {
                "name": "context",
                "type": "string",
                "required": False,
                "description": "Contexto de soporte",
                "default": "Contexto inicial",
            },
        ]
    if "context_items" in name:
        return [
            "Presupuesto limitado",
            "Tiempo de entrega de 8 semanas",
            "Dependencias externas criticas",
        ]
    if "evidence" in name or "sources" in name:
        return [
            {
                "id": "src-1",
                "title": "Informe de mercado",
                "url": "https://example.local/source-1",
                "reliability": 0.8,
            }
        ]
    return [
        {
            "id": "item-1",
            "label": "Item de prueba",
            "description": "Elemento generado para test E2E",
        }
    ]


def _default_object_for_field(field_name: str) -> dict[str, Any]:
    name = field_name.lower()

    if "normalized_request" in name:
        return {
            "raw_request": "Evaluar alternativas y proponer la mejor opcion.",
            "detected_intent": "decision_support",
        }
    if "selected_option" in name:
        return {
            "id": "opt-1",
            "label": "Lanzar MVP",
            "description": "Estrategia incremental",
        }
    if "criteria" in name:
        return {
            "impacto": 1.0,
            "riesgo": 1.0,
            "costo": 0.8,
        }
    if "constraints" in name:
        return {
            "budget": 500000,
            "timeline_weeks": 8,
        }
    if "context" in name:
        return {
            "market": "ES",
            "team_size": 5,
            "domain_experience": "baja",
        }
    if "output" in name:
        return {
            "recommendation": "Lanzar MVP",
            "confidence_score": 0.63,
        }
    if "input" in name:
        return {
            "goal": "Definir estrategia de lanzamiento",
            "context": "Mercado competitivo",
        }
    return {
        "id": "obj-1",
        "text": "Objeto de prueba para validacion de contrato.",
    }


def _generate_value(field_name: str, field_type: str) -> Any:
    if field_type == "string":
        return _default_string_for_field(field_name)
    if field_type == "number":
        return _default_number_for_field(field_name)
    if field_type == "boolean":
        return True
    if field_type == "array":
        return _default_array_for_field(field_name)
    if field_type == "object":
        return _default_object_for_field(field_name)
    return f"valor de prueba ({field_type})"


def _build_inputs(capability: dict[str, Any]) -> dict[str, Any]:
    inputs = capability.get("inputs") or {}
    metadata = capability.get("metadata") or {}
    examples = metadata.get("examples") if isinstance(metadata, dict) else None

    payload: dict[str, Any] = {}
    if isinstance(examples, list) and examples:
        first = examples[0]
        if isinstance(first, dict) and isinstance(first.get("inputs"), dict):
            payload.update(first["inputs"])

    for field_name, spec in inputs.items():
        if not isinstance(spec, dict):
            continue
        if not spec.get("required", False):
            continue
        if field_name in payload:
            continue
        field_type = str(spec.get("type", "string"))
        payload[field_name] = _generate_value(field_name, field_type)

    return payload


def _matches_type(expected_type: str, value: Any) -> bool:
    if expected_type == "string":
        return isinstance(value, str)
    if expected_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected_type == "boolean":
        return isinstance(value, bool)
    if expected_type == "array":
        return isinstance(value, list)
    if expected_type == "object":
        return isinstance(value, dict)
    return True


def _has_substance(expected_type: str, value: Any) -> bool:
    if expected_type == "string":
        return isinstance(value, str) and value.strip() != ""
    if expected_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected_type == "boolean":
        return isinstance(value, bool)
    if expected_type == "array":
        return isinstance(value, list) and len(value) > 0
    if expected_type == "object":
        return isinstance(value, dict) and len(value) > 0
    return value is not None


def _validate_output_contract(
    capability: dict[str, Any],
    output_payload: dict[str, Any],
) -> list[str]:
    outputs = capability.get("outputs") or {}
    errors: list[str] = []

    for field_name, spec in outputs.items():
        if not isinstance(spec, dict):
            continue

        expected_type = str(spec.get("type", "string"))
        required = bool(spec.get("required", False))

        if required and field_name not in output_payload:
            errors.append(f"missing required output: {field_name}")
            continue

        if field_name not in output_payload:
            continue

        value = output_payload[field_name]

        if not _matches_type(expected_type, value):
            errors.append(
                f"type mismatch for {field_name}: expected {expected_type}, got {type(value).__name__}"
            )
            continue

        if required and not _has_substance(expected_type, value):
            errors.append(
                f"required output lacks substance: {field_name} ({expected_type})"
            )

    return errors


def _execute_all_cognitive_capabilities() -> list[CapabilityRunResult]:
    capabilities = _load_active_cognitive_capabilities()
    results: list[CapabilityRunResult] = []

    original_openai_key = os.environ.pop("OPENAI_API_KEY", None)

    try:
        reset()
        for capability in capabilities:
            capability_id = str(capability.get("id"))
            payload = _build_inputs(capability)
            try:
                output = execute_capability(capability_id, payload)
                errors = _validate_output_contract(capability, output)
                status = "passed" if not errors else "failed"
                results.append(
                    CapabilityRunResult(
                        capability_id=capability_id,
                        status=status,
                        errors=errors,
                        input_payload=payload,
                        output_payload=output,
                    )
                )
            except Exception as exc:
                results.append(
                    CapabilityRunResult(
                        capability_id=capability_id,
                        status="failed",
                        errors=[f"execution exception: {type(exc).__name__}: {exc}"],
                        input_payload=payload,
                        output_payload=None,
                        exception_type=type(exc).__name__,
                        exception_message=str(exc),
                    )
                )
    finally:
        if original_openai_key is not None:
            os.environ["OPENAI_API_KEY"] = original_openai_key
        reset()

    return results


def _write_report(results: list[CapabilityRunResult]) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    failures = [r for r in results if r.status != "passed"]

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total": len(results),
        "passed": len(results) - len(failures),
        "failed": len(failures),
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
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def test_all_cognitive_capabilities_end_to_end_contracts() -> None:
    results = _execute_all_cognitive_capabilities()
    _write_report(results)

    failures = [r for r in results if r.status != "passed"]
    if failures:
        first_failures = ", ".join(r.capability_id for r in failures[:10])
        raise AssertionError(
            f"{len(failures)} cognitive capabilities failed contract/result checks. "
            f"First failures: {first_failures}. See {REPORT_PATH.as_posix()}"
        )

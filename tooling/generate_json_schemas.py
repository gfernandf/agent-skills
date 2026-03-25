"""Generate JSON Schema files from runtime dataclasses.

Usage:
    python tooling/generate_json_schemas.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

# ── Schema definitions ───────────────────────────────────────────
# We manually define the JSON Schemas for the public-facing models
# to ensure they are exact, stable contracts — not auto-inferred.

_SCHEMA_DIR = Path(__file__).resolve().parent.parent / "docs" / "schemas"

SCHEMAS: dict[str, dict[str, Any]] = {
    "ExecutionState": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "agent-skills://schemas/ExecutionState",
        "title": "ExecutionState",
        "description": "Mutable state for a single skill execution.",
        "type": "object",
        "required": ["skill_id", "inputs", "status"],
        "properties": {
            "skill_id": {"type": "string"},
            "inputs": {"type": "object"},
            "vars": {"type": "object"},
            "outputs": {"type": "object"},
            "step_results": {
                "type": "object",
                "additionalProperties": {"$ref": "StepResult.schema.json"},
            },
            "events": {
                "type": "array",
                "items": {"$ref": "RuntimeEvent.schema.json"},
            },
            "started_at": {"type": ["string", "null"], "format": "date-time"},
            "finished_at": {"type": ["string", "null"], "format": "date-time"},
            "status": {
                "type": "string",
                "enum": ["pending", "running", "completed", "failed"],
            },
            "trace_id": {"type": ["string", "null"]},
            "frame": {"$ref": "FrameState.schema.json"},
            "working": {"$ref": "WorkingState.schema.json"},
            "output": {"$ref": "OutputState.schema.json"},
            "trace": {"$ref": "TraceState.schema.json"},
            "state_version": {"type": "string"},
            "iteration": {"type": "integer"},
            "current_step": {"type": ["string", "null"]},
            "updated_at": {"type": ["string", "null"], "format": "date-time"},
        },
    },
    "FrameState": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "agent-skills://schemas/FrameState",
        "title": "FrameState",
        "description": "Immutable reasoning context for a run.",
        "type": "object",
        "properties": {
            "goal": {"type": ["string", "null"]},
            "context": {"type": "object"},
            "constraints": {"type": "object"},
            "success_criteria": {"type": "object"},
            "assumptions": {"type": "array", "items": {"type": "string"}},
            "priority": {"type": ["string", "null"]},
        },
    },
    "WorkingState": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "agent-skills://schemas/WorkingState",
        "title": "WorkingState",
        "description": "Mutable working memory for multi-step cognitive processing.",
        "type": "object",
        "properties": {
            "artifacts": {"type": "object"},
            "entities": {"type": "array", "items": {"type": "object"}},
            "options": {"type": "array", "items": {"type": "object"}},
            "criteria": {"type": "array", "items": {"type": "object"}},
            "evidence": {"type": "array", "items": {"type": "object"}},
            "risks": {"type": "array", "items": {"type": "object"}},
            "hypotheses": {"type": "array", "items": {"type": "object"}},
            "uncertainties": {"type": "array", "items": {"type": "object"}},
            "intermediate_decisions": {"type": "array", "items": {"type": "object"}},
            "messages": {"type": "array", "items": {"type": "object"}},
        },
    },
    "OutputState": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "agent-skills://schemas/OutputState",
        "title": "OutputState",
        "description": "Structured result metadata for a run.",
        "type": "object",
        "properties": {
            "result": {},
            "result_type": {"type": ["string", "null"]},
            "summary": {"type": ["string", "null"]},
            "status_reason": {"type": ["string", "null"]},
        },
    },
    "TraceState": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "agent-skills://schemas/TraceState",
        "title": "TraceState",
        "description": "Execution trace for observability and data lineage.",
        "type": "object",
        "properties": {
            "steps": {
                "type": "array",
                "items": {"$ref": "TraceStep.schema.json"},
            },
            "metrics": {"$ref": "TraceMetrics.schema.json"},
        },
    },
    "TraceStep": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "agent-skills://schemas/TraceStep",
        "title": "TraceStep",
        "description": "One step's trace entry with data lineage.",
        "type": "object",
        "required": ["step_id", "capability_id", "status"],
        "properties": {
            "step_id": {"type": "string"},
            "capability_id": {"type": "string"},
            "status": {"type": "string"},
            "started_at": {"type": ["string", "null"], "format": "date-time"},
            "ended_at": {"type": ["string", "null"], "format": "date-time"},
            "reads": {"type": "array", "items": {"type": "string"}},
            "writes": {"type": "array", "items": {"type": "string"}},
            "latency_ms": {"type": ["integer", "null"]},
        },
    },
    "TraceMetrics": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "agent-skills://schemas/TraceMetrics",
        "title": "TraceMetrics",
        "description": "Live aggregate execution metrics.",
        "type": "object",
        "properties": {
            "step_count": {"type": "integer"},
            "llm_calls": {"type": "integer"},
            "tool_calls": {"type": "integer"},
            "tokens_in": {"type": "integer"},
            "tokens_out": {"type": "integer"},
            "elapsed_ms": {"type": "integer"},
        },
    },
    "StepResult": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "agent-skills://schemas/StepResult",
        "title": "StepResult",
        "description": "Execution result for a single step.",
        "type": "object",
        "required": ["step_id", "uses", "status"],
        "properties": {
            "step_id": {"type": "string"},
            "uses": {"type": "string"},
            "status": {"type": "string", "enum": ["completed", "failed", "degraded", "skipped"]},
            "resolved_input": {"type": "object"},
            "produced_output": {"type": ["object", "null"]},
            "binding_id": {"type": ["string", "null"]},
            "service_id": {"type": ["string", "null"]},
            "attempts_count": {"type": ["integer", "null"]},
            "fallback_used": {"type": ["boolean", "null"]},
            "conformance_profile": {"type": ["string", "null"]},
            "error_message": {"type": ["string", "null"]},
            "started_at": {"type": ["string", "null"], "format": "date-time"},
            "finished_at": {"type": ["string", "null"], "format": "date-time"},
            "reads": {"type": ["array", "null"], "items": {"type": "string"}},
            "writes": {"type": ["array", "null"], "items": {"type": "string"}},
            "latency_ms": {"type": ["integer", "null"]},
        },
    },
    "RuntimeEvent": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "agent-skills://schemas/RuntimeEvent",
        "title": "RuntimeEvent",
        "description": "Lightweight execution event for tracing and inspection.",
        "type": "object",
        "required": ["type", "message", "timestamp"],
        "properties": {
            "type": {"type": "string"},
            "message": {"type": "string"},
            "timestamp": {"type": "string", "format": "date-time"},
            "step_id": {"type": ["string", "null"]},
            "trace_id": {"type": ["string", "null"]},
            "data": {"type": "object"},
        },
    },
    "SkillSpec": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "agent-skills://schemas/SkillSpec",
        "title": "SkillSpec",
        "description": "Runtime-normalized skill definition.",
        "type": "object",
        "required": ["id", "version", "name", "description", "inputs", "outputs", "steps"],
        "properties": {
            "id": {"type": "string"},
            "version": {"type": "string"},
            "name": {"type": "string"},
            "description": {"type": "string"},
            "inputs": {
                "type": "object",
                "additionalProperties": {"$ref": "FieldSpec.schema.json"},
            },
            "outputs": {
                "type": "object",
                "additionalProperties": {"$ref": "FieldSpec.schema.json"},
            },
            "steps": {
                "type": "array",
                "items": {"$ref": "StepSpec.schema.json"},
            },
            "metadata": {"type": "object"},
            "channel": {"type": ["string", "null"]},
            "domain": {"type": ["string", "null"]},
        },
    },
    "StepSpec": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "agent-skills://schemas/StepSpec",
        "title": "StepSpec",
        "description": "Declarative execution step inside a skill.",
        "type": "object",
        "required": ["id", "uses"],
        "properties": {
            "id": {"type": "string"},
            "uses": {"type": "string"},
            "input_mapping": {"type": "object"},
            "output_mapping": {"type": "object", "additionalProperties": {"type": "string"}},
            "config": {"type": "object"},
        },
    },
    "FieldSpec": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "agent-skills://schemas/FieldSpec",
        "title": "FieldSpec",
        "description": "Declarative description of an input/output field.",
        "type": "object",
        "required": ["type"],
        "properties": {
            "type": {"type": "string"},
            "required": {"type": "boolean"},
            "description": {"type": ["string", "null"]},
            "default": {},
        },
    },
    "CapabilitySpec": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "agent-skills://schemas/CapabilitySpec",
        "title": "CapabilitySpec",
        "description": "Runtime-normalized capability definition.",
        "type": "object",
        "required": ["id", "version", "description", "inputs", "outputs"],
        "properties": {
            "id": {"type": "string"},
            "version": {"type": "string"},
            "description": {"type": "string"},
            "inputs": {
                "type": "object",
                "additionalProperties": {"$ref": "FieldSpec.schema.json"},
            },
            "outputs": {
                "type": "object",
                "additionalProperties": {"$ref": "FieldSpec.schema.json"},
            },
            "metadata": {"type": "object"},
            "properties": {"type": "object"},
            "requires": {"type": "array", "items": {"type": "string"}},
            "deprecated": {"type": ["boolean", "null"]},
            "replacement": {"type": ["string", "null"]},
            "aliases": {"type": "array", "items": {"type": "string"}},
            "cognitive_hints": {"type": ["object", "null"]},
            "safety": {"type": ["object", "null"]},
        },
    },
    "ExecutionOptions": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "agent-skills://schemas/ExecutionOptions",
        "title": "ExecutionOptions",
        "description": "Runtime behavior switches for a skill execution.",
        "type": "object",
        "properties": {
            "fail_fast": {"type": "boolean", "default": True},
            "max_skill_depth": {"type": "integer", "default": 10},
            "include_raw_step_results": {"type": "boolean", "default": True},
            "trace_enabled": {"type": "boolean", "default": True},
            "required_conformance_profile": {"type": ["string", "null"]},
            "audit_mode": {"type": ["string", "null"]},
            "trust_level": {"type": "string", "default": "standard", "enum": ["sandbox", "standard", "elevated", "privileged"]},
            "max_lineage_timeout_seconds": {"type": ["number", "null"]},
            "max_workers": {"type": ["integer", "null"]},
            "default_step_timeout_seconds": {"type": ["number", "null"]},
        },
    },
    "WebhookSubscription": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "agent-skills://schemas/WebhookSubscription",
        "title": "WebhookSubscription",
        "description": "Webhook subscription for event delivery.",
        "type": "object",
        "required": ["id", "url", "events"],
        "properties": {
            "id": {"type": "string"},
            "url": {"type": "string", "format": "uri"},
            "events": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": ["skill.started", "skill.completed", "skill.failed", "run.completed", "run.failed", "*"],
                },
            },
            "secret": {"type": "string"},
            "active": {"type": "boolean"},
        },
    },
}


def main() -> None:
    _SCHEMA_DIR.mkdir(parents=True, exist_ok=True)
    for name, schema in SCHEMAS.items():
        path = _SCHEMA_DIR / f"{name}.schema.json"
        path.write_text(json.dumps(schema, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Generated {len(SCHEMAS)} schemas in {_SCHEMA_DIR}")


if __name__ == "__main__":
    main()

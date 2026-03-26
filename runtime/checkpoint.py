"""
Checkpoint / Restore for ExecutionState.

Serializes an ExecutionState to a JSON-compatible dict and restores it back,
enabling persistence, migration, and crash-recovery of in-flight runs.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from .models import (
    ExecutionState,
    FrameState,
    OutputState,
    RuntimeEvent,
    StepResult,
    TraceMetrics,
    TraceState,
    TraceStep,
    WorkingState,
)

_CHECKPOINT_FORMAT_VERSION = 1

_ISO = "%Y-%m-%dT%H:%M:%S.%f%z"


# ── helpers ────────────────────────────────────────────────────

def _dt_to_str(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _str_to_dt(s: str | None) -> datetime | None:
    if s is None:
        return None
    return datetime.fromisoformat(s)


# ── serialize ──────────────────────────────────────────────────

def _serialize_step_result(sr: StepResult) -> dict[str, Any]:
    return {
        "step_id": sr.step_id,
        "uses": sr.uses,
        "status": sr.status,
        "resolved_input": sr.resolved_input,
        "produced_output": sr.produced_output,
        "raw_result": sr.raw_result,
        "binding_id": sr.binding_id,
        "service_id": sr.service_id,
        "attempts_count": sr.attempts_count,
        "fallback_used": sr.fallback_used,
        "conformance_profile": sr.conformance_profile,
        "required_conformance_profile": sr.required_conformance_profile,
        "error_message": sr.error_message,
        "started_at": _dt_to_str(sr.started_at),
        "finished_at": _dt_to_str(sr.finished_at),
        "reads": list(sr.reads) if sr.reads else None,
        "writes": list(sr.writes) if sr.writes else None,
        "latency_ms": sr.latency_ms,
    }


def _serialize_event(ev: RuntimeEvent) -> dict[str, Any]:
    return {
        "type": ev.type,
        "message": ev.message,
        "timestamp": _dt_to_str(ev.timestamp),
        "step_id": ev.step_id,
        "trace_id": ev.trace_id,
        "data": ev.data,
    }


def _serialize_trace_step(ts: TraceStep) -> dict[str, Any]:
    return {
        "step_id": ts.step_id,
        "capability_id": ts.capability_id,
        "status": ts.status,
        "started_at": _dt_to_str(ts.started_at),
        "ended_at": _dt_to_str(ts.ended_at),
        "reads": list(ts.reads),
        "writes": list(ts.writes),
        "latency_ms": ts.latency_ms,
    }


def _serialize_frame(f: FrameState) -> dict[str, Any]:
    return {
        "goal": f.goal,
        "context": f.context,
        "constraints": f.constraints,
        "success_criteria": f.success_criteria,
        "assumptions": list(f.assumptions),
        "priority": f.priority,
    }


def _serialize_working(w: WorkingState) -> dict[str, Any]:
    return {
        "artifacts": w.artifacts,
        "entities": w.entities,
        "options": w.options,
        "criteria": w.criteria,
        "evidence": w.evidence,
        "risks": w.risks,
        "hypotheses": w.hypotheses,
        "uncertainties": w.uncertainties,
        "intermediate_decisions": w.intermediate_decisions,
        "messages": w.messages,
    }


def _serialize_output(o: OutputState) -> dict[str, Any]:
    return {
        "result": o.result,
        "result_type": o.result_type,
        "summary": o.summary,
        "status_reason": o.status_reason,
    }


def _serialize_trace(t: TraceState) -> dict[str, Any]:
    m = t.metrics
    return {
        "steps": [_serialize_trace_step(s) for s in t.steps],
        "metrics": {
            "step_count": m.step_count,
            "llm_calls": m.llm_calls,
            "tool_calls": m.tool_calls,
            "tokens_in": m.tokens_in,
            "tokens_out": m.tokens_out,
            "elapsed_ms": m.elapsed_ms,
        },
    }


def state_to_dict(state: ExecutionState) -> dict[str, Any]:
    """Convert an ExecutionState to a JSON-serializable dict."""
    return {
        "_checkpoint_version": _CHECKPOINT_FORMAT_VERSION,
        "skill_id": state.skill_id,
        "inputs": state.inputs,
        "vars": state.vars,
        "outputs": state.outputs,
        "step_results": {
            k: _serialize_step_result(v) for k, v in state.step_results.items()
        },
        "written_targets": sorted(state.written_targets),
        "events": [_serialize_event(e) for e in state.events],
        "started_at": _dt_to_str(state.started_at),
        "finished_at": _dt_to_str(state.finished_at),
        "status": state.status,
        "trace_id": state.trace_id,
        "frame": _serialize_frame(state.frame),
        "working": _serialize_working(state.working),
        "output": _serialize_output(state.output),
        "trace": _serialize_trace(state.trace),
        "extensions": state.extensions,
        "state_version": state.state_version,
        "skill_version": state.skill_version,
        "iteration": state.iteration,
        "current_step": state.current_step,
        "parent_run_id": state.parent_run_id,
        "updated_at": _dt_to_str(state.updated_at),
    }


# ── deserialize ────────────────────────────────────────────────

def _restore_step_result(d: dict[str, Any]) -> StepResult:
    return StepResult(
        step_id=d["step_id"],
        uses=d["uses"],
        status=d["status"],
        resolved_input=d["resolved_input"],
        produced_output=d.get("produced_output"),
        raw_result=d.get("raw_result"),
        binding_id=d.get("binding_id"),
        service_id=d.get("service_id"),
        attempts_count=d.get("attempts_count"),
        fallback_used=d.get("fallback_used"),
        conformance_profile=d.get("conformance_profile"),
        required_conformance_profile=d.get("required_conformance_profile"),
        error_message=d.get("error_message"),
        started_at=_str_to_dt(d.get("started_at")),
        finished_at=_str_to_dt(d.get("finished_at")),
        reads=tuple(d["reads"]) if d.get("reads") else None,
        writes=tuple(d["writes"]) if d.get("writes") else None,
        latency_ms=d.get("latency_ms"),
    )


def _restore_event(d: dict[str, Any]) -> RuntimeEvent:
    return RuntimeEvent(
        type=d["type"],
        message=d["message"],
        timestamp=_str_to_dt(d["timestamp"]),
        step_id=d.get("step_id"),
        trace_id=d.get("trace_id"),
        data=d.get("data", {}),
    )


def _restore_frame(d: dict[str, Any]) -> FrameState:
    return FrameState(
        goal=d.get("goal"),
        context=d.get("context", {}),
        constraints=d.get("constraints", {}),
        success_criteria=d.get("success_criteria", {}),
        assumptions=tuple(d.get("assumptions", ())),
        priority=d.get("priority"),
    )


def _restore_working(d: dict[str, Any]) -> WorkingState:
    return WorkingState(
        artifacts=d.get("artifacts", {}),
        entities=d.get("entities", []),
        options=d.get("options", []),
        criteria=d.get("criteria", []),
        evidence=d.get("evidence", []),
        risks=d.get("risks", []),
        hypotheses=d.get("hypotheses", []),
        uncertainties=d.get("uncertainties", []),
        intermediate_decisions=d.get("intermediate_decisions", []),
        messages=d.get("messages", []),
    )


def _restore_output(d: dict[str, Any]) -> OutputState:
    return OutputState(
        result=d.get("result"),
        result_type=d.get("result_type"),
        summary=d.get("summary"),
        status_reason=d.get("status_reason"),
    )


def _restore_trace_step(d: dict[str, Any]) -> TraceStep:
    return TraceStep(
        step_id=d["step_id"],
        capability_id=d["capability_id"],
        status=d["status"],
        started_at=_str_to_dt(d.get("started_at")),
        ended_at=_str_to_dt(d.get("ended_at")),
        reads=tuple(d.get("reads", ())),
        writes=tuple(d.get("writes", ())),
        latency_ms=d.get("latency_ms"),
    )


def _restore_trace(d: dict[str, Any]) -> TraceState:
    m = d.get("metrics", {})
    return TraceState(
        steps=[_restore_trace_step(s) for s in d.get("steps", [])],
        metrics=TraceMetrics(
            step_count=m.get("step_count", 0),
            llm_calls=m.get("llm_calls", 0),
            tool_calls=m.get("tool_calls", 0),
            tokens_in=m.get("tokens_in", 0),
            tokens_out=m.get("tokens_out", 0),
            elapsed_ms=m.get("elapsed_ms", 0),
        ),
    )


def dict_to_state(d: dict[str, Any]) -> ExecutionState:
    """Restore an ExecutionState from a dict produced by state_to_dict."""
    return ExecutionState(
        skill_id=d["skill_id"],
        inputs=d["inputs"],
        vars=d.get("vars", {}),
        outputs=d.get("outputs", {}),
        step_results={
            k: _restore_step_result(v)
            for k, v in d.get("step_results", {}).items()
        },
        written_targets=set(d.get("written_targets", [])),
        events=[_restore_event(e) for e in d.get("events", [])],
        started_at=_str_to_dt(d.get("started_at")),
        finished_at=_str_to_dt(d.get("finished_at")),
        status=d.get("status", "pending"),
        trace_id=d.get("trace_id"),
        frame=_restore_frame(d.get("frame", {})),
        working=_restore_working(d.get("working", {})),
        output=_restore_output(d.get("output", {})),
        trace=_restore_trace(d.get("trace", {})),
        extensions=d.get("extensions", {}),
        state_version=d.get("state_version", "1.0.0"),
        skill_version=d.get("skill_version"),
        iteration=d.get("iteration", 0),
        current_step=d.get("current_step"),
        parent_run_id=d.get("parent_run_id"),
        updated_at=_str_to_dt(d.get("updated_at")),
    )


# ── convenience I/O ────────────────────────────────────────────

def save_checkpoint(state: ExecutionState, path: str) -> None:
    """Serialize an ExecutionState to a JSON file."""
    import pathlib

    data = state_to_dict(state)
    pathlib.Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def load_checkpoint(path: str) -> ExecutionState:
    """Restore an ExecutionState from a JSON checkpoint file."""
    import pathlib

    raw = pathlib.Path(path).read_text(encoding="utf-8")
    return dict_to_state(json.loads(raw))

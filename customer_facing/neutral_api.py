from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from runtime.engine_factory import RuntimeComponents, build_runtime_components
from runtime.errors import (
    CheckpointNotFoundError,
    IdempotencyConflictError,
    RunNotFoundError,
    SafetyConfirmationRequiredError,
)
from runtime.execution_state import create_execution_state, mark_started
from runtime.models import ExecutionOptions, ExecutionRequest
from runtime.openapi_error_contract import map_runtime_error_to_http


def _error_response(error: Exception, *, trace_id: str | None = None) -> dict[str, Any]:
    """Build a protocol-neutral error dict consistent with the HTTP error contract."""
    contract = map_runtime_error_to_http(error)
    return {
        "error": {
            "code": contract.code,
            "message": contract.message,
            "type": contract.type,
            "status": contract.status_code,
        },
        "trace_id": trace_id,
    }


def _ok_response(payload: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, "data": payload}


def _project_legacy_run_status(run: dict[str, Any]) -> dict[str, Any]:
    """Legacy projection for aliases expecting old status taxonomy."""
    projected = dict(run)
    if projected.get("status") == "canceled":
        projected["status"] = "failed"
    return projected


def _build_step_diagnostics(result) -> dict[str, Any]:
    from sdk.embedded import _build_skill_execution_meta

    return _build_skill_execution_meta(result)


def _calibrate_execution_confidence(
    *,
    skill_id: str,
    outputs: dict[str, Any],
    meta: dict[str, Any],
) -> dict[str, Any]:
    from sdk.embedded import apply_execution_reliability_confidence_calibration

    if not isinstance(outputs, dict):
        return outputs
    if not isinstance(meta, dict):
        return outputs
    return apply_execution_reliability_confidence_calibration(
        skill_id=skill_id,
        outputs=outputs,
        meta=meta,
    )


def _build_async_idempotency_fingerprint(
    *,
    skill_id: str,
    inputs: dict[str, Any],
    required_conformance_profile: str | None,
    audit_mode: str | None,
    execution_channel: str | None,
) -> str:
    payload = {
        "skill_id": skill_id,
        "inputs": inputs,
        "required_conformance_profile": required_conformance_profile,
        "audit_mode": audit_mode,
        "execution_channel": execution_channel,
    }
    normalized = json.dumps(payload, sort_keys=True, ensure_ascii=True, default=str)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class NeutralRuntimeAPI:
    """
    Protocol-neutral customer-facing facade.

    This API intentionally exposes domain operations (execute/describe/health)
    without transport-specific assumptions (HTTP, MCP, SDK, etc.).
    """

    def __init__(
        self,
        registry_root: Path,
        runtime_root: Path,
        host_root: Path,
        *,
        mcp_client_registry: Any | None = None,
    ) -> None:
        self.registry_root = registry_root
        self.runtime_root = runtime_root
        self.host_root = host_root
        self.components: RuntimeComponents = build_runtime_components(
            registry_root=registry_root,
            runtime_root=runtime_root,
            host_root=host_root,
            mcp_client_registry=mcp_client_registry,
        )

    def health(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "registry_root": str(self.registry_root),
            "runtime_root": str(self.runtime_root),
        }

    def list_skill_governance(
        self,
        *,
        min_state: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """
        Read the operational skill quality artifact and return filtered entries.
        """
        rank = {
            "draft": 0,
            "validated": 1,
            "lab-verified": 2,
            "trusted": 3,
            "recommended": 4,
        }

        artifact = self.runtime_root / "artifacts" / "skill_quality.json"
        if not artifact.exists():
            return {
                "source": str(artifact),
                "summary": {"total_skills": 0, "by_state": {}},
                "skills": [],
                "warning": "skill quality artifact not found; run tooling/build_skill_quality_catalog.py",
            }

        raw = json.loads(artifact.read_text(encoding="utf-8"))
        skills = raw.get("skills", []) if isinstance(raw, dict) else []
        if not isinstance(skills, list):
            skills = []

        min_rank = 0
        if isinstance(min_state, str) and min_state:
            min_rank = rank.get(min_state, 0)

        filtered = [
            s
            for s in skills
            if isinstance(s, dict)
            and rank.get(str(s.get("lifecycle_state")), -1) >= min_rank
        ]

        try:
            limit_int = max(1, int(limit))
        except Exception:
            limit_int = 20

        return {
            "source": str(artifact),
            "summary": raw.get("summary", {}) if isinstance(raw, dict) else {},
            "skills": filtered[:limit_int],
            "min_state": min_state,
            "limit": limit_int,
        }

    def describe_skill(self, skill_id: str) -> dict[str, Any]:
        try:
            skill = self.components.skill_loader.get_skill(skill_id)
        except Exception as exc:
            return _error_response(exc)
        return {
            "id": skill.id,
            "version": skill.version,
            "name": skill.name,
            "description": skill.description,
            "inputs": {k: asdict(v) for k, v in skill.inputs.items()},
            "outputs": {k: asdict(v) for k, v in skill.outputs.items()},
            "steps": [
                {
                    "id": s.id,
                    "uses": s.uses,
                    "input": s.input_mapping,
                    "output": s.output_mapping,
                }
                for s in skill.steps
            ],
        }

    def execute_skill(
        self,
        skill_id: str,
        inputs: dict[str, Any] | None,
        *,
        trace_id: str | None = None,
        include_trace: bool = False,
        required_conformance_profile: str | None = None,
        audit_mode: str | None = None,
        execution_channel: str | None = None,
        trace_callback=None,
    ) -> dict[str, Any]:
        try:
            _, payload = self._execute_skill_with_result(
                skill_id=skill_id,
                inputs=inputs,
                trace_id=trace_id,
                include_trace=include_trace,
                required_conformance_profile=required_conformance_profile,
                audit_mode=audit_mode,
                execution_channel=execution_channel,
                trace_callback=trace_callback,
            )
            return payload
        except Exception as exc:
            return _error_response(exc, trace_id=trace_id)

    def _execute_skill_with_result(
        self,
        *,
        skill_id: str,
        inputs: dict[str, Any] | None,
        trace_id: str | None,
        include_trace: bool,
        required_conformance_profile: str | None,
        audit_mode: str | None,
        execution_channel: str | None,
        confirmed_capabilities: list[str] | None = None,
        initial_state=None,
        trace_callback=None,
        propagate_safety_confirmation: bool = False,
    ) -> tuple[Any, dict[str, Any]]:
        request = ExecutionRequest(
            skill_id=skill_id,
            inputs=inputs or {},
            options=ExecutionOptions(
                required_conformance_profile=required_conformance_profile,
                audit_mode=audit_mode,
                confirmed_capabilities=frozenset(
                    item
                    for item in (confirmed_capabilities or [])
                    if isinstance(item, str)
                ),
            ),
            trace_id=trace_id,
            channel=execution_channel,
            initial_state=initial_state,
        )

        try:
            result = self.components.engine.execute(
                request,
                trace_callback=trace_callback,
            )
        except SafetyConfirmationRequiredError:
            if propagate_safety_confirmation:
                raise
            raise

        outputs = dict(result.outputs) if isinstance(result.outputs, dict) else {}
        meta = _build_step_diagnostics(result)
        outputs = _calibrate_execution_confidence(
            skill_id=result.skill_id,
            outputs=outputs,
            meta=meta,
        )

        payload: dict[str, Any] = {
            "skill_id": result.skill_id,
            "status": result.status,
            "outputs": outputs,
            "trace_id": result.state.trace_id,
            "meta": meta,
        }

        if include_trace:
            payload["events"] = [
                {
                    "type": ev.type,
                    "message": ev.message,
                    "timestamp": ev.timestamp.isoformat() + "Z",
                    "step_id": ev.step_id,
                    "trace_id": ev.trace_id,
                    "data": ev.data,
                }
                for ev in result.state.events
            ]

        return result, payload

    def execute_capability(
        self,
        capability_id: str,
        inputs: dict[str, Any] | None,
        *,
        trace_id: str | None = None,
        required_conformance_profile: str | None = None,
    ) -> dict[str, Any]:
        try:
            capability = self.components.capability_loader.get_capability(capability_id)
            result = self.components.capability_executor.execute(
                capability,
                inputs or {},
                trace_id=trace_id,
                required_conformance_profile=required_conformance_profile,
            )
        except Exception as exc:
            return _error_response(exc, trace_id=trace_id)

        if isinstance(result, tuple):
            outputs, meta = result
        else:
            outputs, meta = result, {}

        outputs = _calibrate_execution_confidence(
            skill_id=capability_id,
            outputs=outputs if isinstance(outputs, dict) else {},
            meta=meta if isinstance(meta, dict) else {},
        )

        return {
            "capability_id": capability_id,
            "outputs": outputs,
            "meta": meta,
            "trace_id": trace_id,
        }

    def explain_capability_resolution(
        self,
        capability_id: str,
        *,
        required_conformance_profile: str | None = None,
    ) -> dict[str, Any]:
        try:
            capability = self.components.capability_loader.get_capability(capability_id)
            executor = self.components.capability_executor.binding_executor
            return executor.build_resolution_plan(
                capability=capability,
                required_conformance_profile=required_conformance_profile,
            )
        except Exception as exc:
            return _error_response(exc)

    def metrics(self) -> dict[str, Any]:
        """Return current runtime metrics snapshot."""
        from runtime.metrics import METRICS

        return METRICS.snapshot()

    def execute_skill_streaming(
        self,
        skill_id: str,
        inputs: dict[str, Any] | None,
        event_callback,
        *,
        trace_id: str | None = None,
        required_conformance_profile: str | None = None,
        audit_mode: str | None = None,
        execution_channel: str | None = None,
    ) -> dict[str, Any]:
        """Execute a skill, emitting each engine event via *event_callback*.

        ``event_callback(event_dict)`` is called for every runtime event
        (step_start, step_completed, etc.).  The final result is returned
        normally.
        """
        request = ExecutionRequest(
            skill_id=skill_id,
            inputs=inputs or {},
            options=ExecutionOptions(
                required_conformance_profile=required_conformance_profile,
                audit_mode=audit_mode,
            ),
            trace_id=trace_id,
            channel=execution_channel,
        )

        def _trace_cb(event):
            try:
                event_callback(
                    {
                        "type": event.type,
                        "message": event.message,
                        "timestamp": event.timestamp.isoformat() + "Z",
                        "step_id": event.step_id,
                        "trace_id": event.trace_id,
                        "data": event.data,
                    }
                )
            except Exception:
                pass  # streaming errors must not abort the engine

        try:
            result = self.components.engine.execute(
                request,
                trace_callback=_trace_cb,
            )
        except Exception as exc:
            return _error_response(exc, trace_id=trace_id)

        return {
            "skill_id": result.skill_id,
            "status": result.status,
            "outputs": result.outputs,
            "trace_id": result.state.trace_id,
        }

    # ── Async execution (run store) ──────────────────────────────────────

    def execute_skill_async(
        self,
        skill_id: str,
        inputs: dict[str, Any] | None,
        *,
        trace_id: str | None = None,
        idempotency_key: str | None = None,
        idempotency_ttl_seconds: int | None = 86400,
        required_conformance_profile: str | None = None,
        audit_mode: str | None = None,
        execution_channel: str | None = None,
        run_store=None,
        checkpoint_manager=None,
        async_pool=None,
        webhook_store=None,
    ) -> dict[str, Any]:
        """Launch skill execution asynchronously.  Returns run metadata immediately."""
        if run_store is None:
            return _error_response(
                RuntimeError("RunStore not configured"), trace_id=trace_id
            )

        normalized_idempotency_key = (
            idempotency_key.strip()
            if isinstance(idempotency_key, str) and idempotency_key.strip()
            else None
        )
        normalized_idempotency_ttl_seconds = None
        if idempotency_ttl_seconds is not None:
            try:
                normalized_idempotency_ttl_seconds = max(
                    0, int(idempotency_ttl_seconds)
                )
            except (TypeError, ValueError):
                normalized_idempotency_ttl_seconds = 86400

        normalized_inputs = dict(inputs or {})
        request_fingerprint = _build_async_idempotency_fingerprint(
            skill_id=skill_id,
            inputs=normalized_inputs,
            required_conformance_profile=required_conformance_profile,
            audit_mode=audit_mode,
            execution_channel=execution_channel,
        )

        if normalized_idempotency_key is not None:
            if normalized_idempotency_ttl_seconds is not None:
                try:
                    run_store.prune_expired_idempotency_keys(
                        normalized_idempotency_ttl_seconds
                    )
                except Exception:
                    pass

            existing_run = run_store.find_run_by_idempotency_key(
                normalized_idempotency_key,
                skill_id=skill_id,
                ttl_seconds=normalized_idempotency_ttl_seconds,
            )
            if isinstance(existing_run, dict):
                existing_metadata = (
                    existing_run.get("metadata")
                    if isinstance(existing_run.get("metadata"), dict)
                    else {}
                )
                existing_fingerprint = (
                    existing_metadata.get("idempotency_fingerprint")
                    if isinstance(existing_metadata.get("idempotency_fingerprint"), str)
                    else None
                )
                if existing_fingerprint and existing_fingerprint != request_fingerprint:
                    return _error_response(
                        IdempotencyConflictError(
                            f"Idempotency key '{normalized_idempotency_key}' conflicts with an existing async request"
                        ),
                        trace_id=trace_id,
                    )
                return {
                    "run_id": existing_run.get("run_id"),
                    "status": existing_run.get("status"),
                    "trace_id": existing_run.get("trace_id"),
                    "checkpoint_head": existing_run.get("checkpoint_head"),
                    "idempotent_replay": True,
                }

        from uuid import uuid4

        run_id = str(uuid4())
        run = run_store.create_run_record(
            run_id=run_id,
            skill_id=skill_id,
            trace_id=trace_id,
            status="running",
            metadata={
                "inputs": normalized_inputs,
                "required_conformance_profile": required_conformance_profile,
                "audit_mode": audit_mode,
                "execution_channel": execution_channel,
                "confirmed_capabilities": [],
                "idempotency_key": normalized_idempotency_key,
                "idempotency_fingerprint": request_fingerprint,
            },
        )

        if checkpoint_manager is not None:
            try:
                state = create_execution_state(skill_id, inputs or {}, trace_id=trace_id)
                mark_started(state)
                checkpoint = checkpoint_manager.save_checkpoint(
                    run_id=run_id,
                    state=state,
                    step_id=None,
                    kind="run_started",
                )
                run_store.patch_run(
                    run_id,
                    {
                        "checkpoint_head": checkpoint.checkpoint_id,
                    },
                )
                run = run_store.get_run(run_id) or run
            except Exception:
                pass

        def _background():
            try:
                result, result_payload = self._execute_skill_with_result(
                    skill_id=skill_id,
                    inputs=inputs,
                    trace_id=trace_id,
                    include_trace=False,
                    required_conformance_profile=required_conformance_profile,
                    audit_mode=audit_mode,
                    execution_channel=execution_channel,
                )

                if checkpoint_manager is not None:
                    try:
                        checkpoint = checkpoint_manager.save_checkpoint(
                            run_id=run_id,
                            state=result.state,
                            step_id=result.state.current_step,
                            kind="run_finished",
                        )
                        run_store.patch_run(
                            run_id,
                            {
                                "checkpoint_head": checkpoint.checkpoint_id,
                                "current_step_id": result.state.current_step,
                            },
                        )
                    except Exception:
                        pass

                run_store.complete_run(run_id, result_payload)
                if webhook_store is not None:
                    try:
                        from runtime.webhook import deliver_event

                        deliver_event(
                            webhook_store,
                            "run.completed",
                            {
                                "run_id": run_id,
                                "skill_id": skill_id,
                                "status": "completed",
                                "result": result_payload,
                            },
                            trace_id=trace_id,
                        )
                    except Exception:
                        pass
            except Exception as exc:
                if isinstance(exc, SafetyConfirmationRequiredError):
                    approval_state = getattr(exc, "execution_state", None)
                    if approval_state is None:
                        approval_state = create_execution_state(
                            skill_id,
                            inputs or {},
                            trace_id=trace_id,
                        )
                        mark_started(approval_state)
                        approval_state.current_step = exc.step_id

                    checkpoint_id = None
                    if checkpoint_manager is not None:
                        try:
                            checkpoint = checkpoint_manager.save_checkpoint(
                                run_id=run_id,
                                state=approval_state,
                                step_id=approval_state.current_step,
                                kind="run_waiting_for_human",
                            )
                            checkpoint_id = checkpoint.checkpoint_id
                        except Exception:
                            checkpoint_id = None

                    waiting = run_store.mark_waiting_for_human(
                        run_id,
                        current_step_id=approval_state.current_step,
                        checkpoint_head=checkpoint_id,
                        approval_request={
                            "reason": "requires_confirmation",
                            "message": str(exc),
                            "capability_id": exc.capability_id,
                            "step_id": exc.step_id,
                        },
                    )
                    if webhook_store is not None:
                        try:
                            from runtime.webhook import deliver_event

                            deliver_event(
                                webhook_store,
                                "run.waiting_for_human",
                                {
                                    "run_id": run_id,
                                    "skill_id": skill_id,
                                    "status": "waiting_for_human",
                                    "approval_request": (
                                        waiting.get("approval_request")
                                        if isinstance(waiting, dict)
                                        else {}
                                    ),
                                },
                                trace_id=trace_id,
                            )
                        except Exception:
                            pass
                    return

                if checkpoint_manager is not None:
                    try:
                        existing_run = run_store.get_run(run_id)
                        fail_state = create_execution_state(
                            skill_id,
                            inputs or {},
                            trace_id=trace_id,
                        )
                        fail_state.status = "failed"
                        checkpoint = checkpoint_manager.save_checkpoint(
                            run_id=run_id,
                            state=fail_state,
                            step_id=(
                                existing_run.get("current_step_id")
                                if isinstance(existing_run, dict)
                                else None
                            ),
                            kind="run_failed",
                        )
                        run_store.patch_run(
                            run_id,
                            {
                                "checkpoint_head": checkpoint.checkpoint_id,
                            },
                        )
                    except Exception:
                        pass

                run_store.fail_run(run_id, str(exc))
                if webhook_store is not None:
                    try:
                        from runtime.webhook import deliver_event

                        deliver_event(
                            webhook_store,
                            "run.failed",
                            {
                                "run_id": run_id,
                                "skill_id": skill_id,
                                "status": "failed",
                                "error": str(exc),
                            },
                            trace_id=trace_id,
                        )
                    except Exception:
                        pass

        if async_pool is not None:
            async_pool.submit(_background)
        else:
            import threading

            threading.Thread(target=_background, daemon=True).start()

        return {
            "run_id": run_id,
            "skill_id": skill_id,
            "status": "running",
            "trace_id": trace_id,
            "checkpoint_head": run.get("checkpoint_head"),
        }

    def get_run(
        self,
        run_id: str,
        *,
        run_store=None,
        legacy_projection: bool = False,
    ) -> dict[str, Any]:
        if run_store is None:
            return _error_response(RuntimeError("RunStore not configured"))
        run = run_store.get_run(run_id)
        if run is None:
            return _error_response(RunNotFoundError(f"Run '{run_id}' not found"))
        if legacy_projection:
            run = _project_legacy_run_status(run)
        return _ok_response(run)

    def cancel_run(
        self,
        run_id: str,
        *,
        run_store=None,
        legacy_projection: bool = False,
    ) -> dict[str, Any]:
        if run_store is None:
            return _error_response(RuntimeError("RunStore not configured"))
        run = run_store.cancel_run(run_id)
        if run is None:
            return _error_response(RunNotFoundError(f"Run '{run_id}' not found"))
        if legacy_projection:
            run = _project_legacy_run_status(run)
        return _ok_response(run)

    def list_checkpoints(
        self,
        run_id: str,
        *,
        run_store=None,
        checkpoint_manager=None,
    ) -> dict[str, Any]:
        if run_store is None:
            return _error_response(RuntimeError("RunStore not configured"))
        if checkpoint_manager is None:
            return _error_response(RuntimeError("CheckpointManager not configured"))

        run = run_store.get_run(run_id)
        if run is None:
            return _error_response(RunNotFoundError(f"Run '{run_id}' not found"))

        checkpoints = checkpoint_manager.list_checkpoints(run_id)
        return _ok_response(
            {
                "run_id": run_id,
                "checkpoints": checkpoints,
                "total": len(checkpoints),
                "checkpoint_head": run.get("checkpoint_head"),
            }
        )

    def resume_run(
        self,
        run_id: str,
        *,
        run_store=None,
        checkpoint_manager=None,
        checkpoint_id: str | None = None,
        confirmed_capabilities: list[str] | None = None,
        async_pool=None,
        webhook_store=None,
    ) -> dict[str, Any]:
        if run_store is None:
            return _error_response(RuntimeError("RunStore not configured"))
        if checkpoint_manager is None:
            return _error_response(RuntimeError("CheckpointManager not configured"))

        run = run_store.get_run(run_id)
        if run is None:
            return _error_response(RunNotFoundError(f"Run '{run_id}' not found"))

        selected_checkpoint_id = checkpoint_id or run.get("checkpoint_head")
        if not isinstance(selected_checkpoint_id, str) or not selected_checkpoint_id:
            return _error_response(
                RuntimeError(
                    f"Run '{run_id}' has no checkpoint to resume from"
                )
            )

        checkpoint = checkpoint_manager.load_checkpoint(
            run_id=run_id,
            checkpoint_id=selected_checkpoint_id,
        )
        if checkpoint is None:
            return _error_response(
                CheckpointNotFoundError(
                    f"Checkpoint '{selected_checkpoint_id}' not found for run '{run_id}'"
                )
            )

        restored_state = checkpoint_manager.load_state(
            run_id=run_id,
            checkpoint_id=selected_checkpoint_id,
        )
        if restored_state is None:
            return _error_response(
                CheckpointNotFoundError(
                    f"Checkpoint state '{selected_checkpoint_id}' not found for run '{run_id}'"
                )
            )

        metadata = run.get("metadata") if isinstance(run.get("metadata"), dict) else {}
        skill_id = run.get("skill_id")
        if not isinstance(skill_id, str) or not skill_id:
            return _error_response(
                RuntimeError(f"Run '{run_id}' is missing skill metadata for resume")
            )
        inputs = metadata.get("inputs") if isinstance(metadata.get("inputs"), dict) else dict(restored_state.inputs)
        trace_id = run.get("trace_id") if isinstance(run.get("trace_id"), str) else restored_state.trace_id
        required_conformance_profile = (
            metadata.get("required_conformance_profile")
            if isinstance(metadata.get("required_conformance_profile"), str)
            else None
        )
        confirmed_existing = metadata.get("confirmed_capabilities")
        combined_confirmed: list[str] = []
        if isinstance(confirmed_existing, list):
            combined_confirmed.extend(
                item for item in confirmed_existing if isinstance(item, str)
            )
        if isinstance(confirmed_capabilities, list):
            for item in confirmed_capabilities:
                if isinstance(item, str) and item not in combined_confirmed:
                    combined_confirmed.append(item)
        audit_mode = metadata.get("audit_mode") if isinstance(metadata.get("audit_mode"), str) else None
        execution_channel = (
            metadata.get("execution_channel")
            if isinstance(metadata.get("execution_channel"), str)
            else "http-resume"
        )

        try:
            updated = run_store.resume_run(
                run_id,
                resume_from_checkpoint_id=selected_checkpoint_id,
            )
        except Exception as exc:
            return _error_response(exc)

        if updated is None:
            return _error_response(RunNotFoundError(f"Run '{run_id}' not found"))

        try:
            resumed_checkpoint = checkpoint_manager.save_checkpoint(
                run_id=run_id,
                state=restored_state,
                step_id=restored_state.current_step,
                kind="run_resumed",
            )
            updated = run_store.patch_run(
                run_id,
                {
                    "checkpoint_head": resumed_checkpoint.checkpoint_id,
                    "current_step_id": restored_state.current_step,
                },
            ) or updated
        except Exception:
            pass

        def _background_resume() -> None:
            try:
                result, result_payload = self._execute_skill_with_result(
                    skill_id=skill_id,
                    inputs=inputs,
                    trace_id=trace_id,
                    include_trace=False,
                    required_conformance_profile=required_conformance_profile,
                    audit_mode=audit_mode,
                    execution_channel=execution_channel,
                    confirmed_capabilities=combined_confirmed,
                    initial_state=restored_state,
                    propagate_safety_confirmation=True,
                )

                try:
                    checkpoint_record = checkpoint_manager.save_checkpoint(
                        run_id=run_id,
                        state=result.state,
                        step_id=result.state.current_step,
                        kind="run_finished",
                    )
                    run_store.patch_run(
                        run_id,
                        {
                            "checkpoint_head": checkpoint_record.checkpoint_id,
                            "current_step_id": result.state.current_step,
                        },
                    )
                except Exception:
                    pass

                run_store.complete_run(run_id, result_payload)
                if webhook_store is not None:
                    try:
                        webhook_store.notify(
                            "run.completed",
                            {
                                "run_id": run_id,
                                "skill_id": skill_id,
                                "status": "completed",
                                "trace_id": trace_id,
                                "resumed_from_checkpoint_id": selected_checkpoint_id,
                            },
                        )
                    except Exception:
                        pass
            except Exception as exc:
                try:
                    checkpoint_record = checkpoint_manager.save_checkpoint(
                        run_id=run_id,
                        state=restored_state,
                        step_id=restored_state.current_step,
                        kind="run_failed",
                    )
                    run_store.patch_run(
                        run_id,
                        {
                            "checkpoint_head": checkpoint_record.checkpoint_id,
                            "current_step_id": restored_state.current_step,
                        },
                    )
                except Exception:
                    pass

                run_store.fail_run(run_id, str(exc))
                if webhook_store is not None:
                    try:
                        webhook_store.notify(
                            "run.failed",
                            {
                                "run_id": run_id,
                                "skill_id": skill_id,
                                "status": "failed",
                                "error": str(exc),
                                "trace_id": trace_id,
                                "resumed_from_checkpoint_id": selected_checkpoint_id,
                            },
                        )
                    except Exception:
                        pass

        if async_pool is not None:
            async_pool.submit(_background_resume)
        else:
            import threading

            thread = threading.Thread(target=_background_resume, daemon=True)
            thread.start()

        return _ok_response(
            {
                "run": updated,
                "resume": {
                    "accepted": True,
                    "mode": "checkpoint_resume",
                    "checkpoint_id": selected_checkpoint_id,
                },
            }
        )

    def approve_run(
        self,
        run_id: str,
        *,
        approver: str | None = None,
        notes: str | None = None,
        run_store=None,
        checkpoint_manager=None,
        async_pool=None,
        webhook_store=None,
    ) -> dict[str, Any]:
        if run_store is None:
            return _error_response(RuntimeError("RunStore not configured"))
        run = run_store.get_run(run_id)
        if run is None:
            return _error_response(RunNotFoundError(f"Run '{run_id}' not found"))
        if run.get("status") != "waiting_for_human":
            return _error_response(
                RuntimeError(f"Run '{run_id}' is not waiting for human approval")
            )

        approval_request = run.get("approval_request")
        capability_id = (
            approval_request.get("capability_id")
            if isinstance(approval_request, dict)
            and isinstance(approval_request.get("capability_id"), str)
            else None
        )
        confirmed_capabilities = [capability_id] if capability_id else []
        updated = run_store.approve_run(
            run_id,
            approver=approver,
            notes=notes,
            confirmed_capabilities=confirmed_capabilities,
            resume_from_checkpoint_id=run.get("checkpoint_head"),
        )
        if updated is None:
            return _error_response(RunNotFoundError(f"Run '{run_id}' not found"))

        return self.resume_run(
            run_id,
            run_store=run_store,
            checkpoint_manager=checkpoint_manager,
            checkpoint_id=run.get("checkpoint_head"),
            confirmed_capabilities=confirmed_capabilities,
            async_pool=async_pool,
            webhook_store=webhook_store,
        )

    def deny_run(
        self,
        run_id: str,
        *,
        approver: str | None = None,
        notes: str | None = None,
        run_store=None,
        legacy_projection: bool = False,
    ) -> dict[str, Any]:
        if run_store is None:
            return _error_response(RuntimeError("RunStore not configured"))
        run = run_store.deny_run(
            run_id,
            approver=approver,
            notes=notes,
        )
        if run is None:
            return _error_response(RunNotFoundError(f"Run '{run_id}' not found"))
        if legacy_projection:
            run = _project_legacy_run_status(run)
        return _ok_response(run)

    def replay_run(
        self,
        run_id: str,
        *,
        run_store=None,
        checkpoint_manager=None,
        checkpoint_id: str | None = None,
        async_pool=None,
        webhook_store=None,
    ) -> dict[str, Any]:
        if run_store is None:
            return _error_response(RuntimeError("RunStore not configured"))
        if checkpoint_manager is None:
            return _error_response(RuntimeError("CheckpointManager not configured"))

        source_run = run_store.get_run(run_id)
        if source_run is None:
            return _error_response(RunNotFoundError(f"Run '{run_id}' not found"))

        selected_checkpoint_id = checkpoint_id or source_run.get("checkpoint_head")
        if not isinstance(selected_checkpoint_id, str) or not selected_checkpoint_id:
            return _error_response(
                RuntimeError(f"Run '{run_id}' has no checkpoint to replay from")
            )

        checkpoint = checkpoint_manager.load_checkpoint(
            run_id=run_id,
            checkpoint_id=selected_checkpoint_id,
        )
        if checkpoint is None:
            return _error_response(
                CheckpointNotFoundError(
                    f"Checkpoint '{selected_checkpoint_id}' not found for run '{run_id}'"
                )
            )

        restored_state = checkpoint_manager.load_state(
            run_id=run_id,
            checkpoint_id=selected_checkpoint_id,
        )
        if restored_state is None:
            return _error_response(
                CheckpointNotFoundError(
                    f"Checkpoint state '{selected_checkpoint_id}' not found for run '{run_id}'"
                )
            )

        source_skill_id = source_run.get("skill_id")
        if not isinstance(source_skill_id, str) or not source_skill_id:
            return _error_response(
                RuntimeError(f"Run '{run_id}' is missing skill metadata for replay")
            )

        from uuid import uuid4

        source_trace_id = source_run.get("trace_id") if isinstance(source_run.get("trace_id"), str) else restored_state.trace_id
        replay_run_id = f"replay_{run_id}_{uuid4().hex[:12]}"
        replay_run = run_store.replay_run(
            replay_run_id,
            skill_id=source_skill_id,
            trace_id=source_trace_id,
            source_run_id=run_id,
            source_checkpoint_id=selected_checkpoint_id,
            checkpoint_head=selected_checkpoint_id,
            metadata={
                "inputs": dict(restored_state.inputs),
                "audit_mode": "replay",
                "execution_channel": source_run.get("execution_channel") if isinstance(source_run.get("execution_channel"), str) else "http-replay",
                "confirmed_capabilities": list((source_run.get("metadata") or {}).get("confirmed_capabilities", [])) if isinstance(source_run.get("metadata"), dict) else [],
            },
        )

        def _background_replay() -> None:
            try:
                updated = run_store.resume_run(
                    replay_run_id,
                    resume_from_checkpoint_id=selected_checkpoint_id,
                )
                if updated is None:
                    raise RuntimeError(f"Replay run '{replay_run_id}' not found")

                result, result_payload = self._execute_skill_with_result(
                    skill_id=source_skill_id,
                    inputs=dict(restored_state.inputs),
                    trace_id=source_trace_id,
                    include_trace=False,
                    required_conformance_profile=(
                        (source_run.get("metadata") or {}).get("required_conformance_profile")
                        if isinstance(source_run.get("metadata"), dict)
                        else None
                    ),
                    audit_mode="replay",
                    execution_channel=source_run.get("execution_channel") if isinstance(source_run.get("execution_channel"), str) else "http-replay",
                    confirmed_capabilities=(source_run.get("metadata") or {}).get("confirmed_capabilities") if isinstance(source_run.get("metadata"), dict) else [],
                    initial_state=restored_state,
                )

                try:
                    checkpoint_record = checkpoint_manager.save_checkpoint(
                        run_id=replay_run_id,
                        state=result.state,
                        step_id=result.state.current_step,
                        kind="run_finished",
                    )
                    run_store.patch_run(
                        replay_run_id,
                        {
                            "checkpoint_head": checkpoint_record.checkpoint_id,
                            "current_step_id": result.state.current_step,
                        },
                    )
                except Exception:
                    pass

                run_store.complete_run(replay_run_id, result_payload)
                if webhook_store is not None:
                    try:
                        webhook_store.notify(
                            "run.replayed",
                            {
                                "run_id": replay_run_id,
                                "source_run_id": run_id,
                                "source_checkpoint_id": selected_checkpoint_id,
                                "skill_id": source_skill_id,
                                "status": "completed",
                            },
                        )
                    except Exception:
                        pass
            except Exception as exc:
                run_store.fail_run(replay_run_id, str(exc))
                if webhook_store is not None:
                    try:
                        webhook_store.notify(
                            "run.failed",
                            {
                                "run_id": replay_run_id,
                                "source_run_id": run_id,
                                "source_checkpoint_id": selected_checkpoint_id,
                                "skill_id": source_skill_id,
                                "status": "failed",
                                "error": str(exc),
                            },
                        )
                    except Exception:
                        pass

        if async_pool is not None:
            async_pool.submit(_background_replay)
        else:
            import threading

            threading.Thread(target=_background_replay, daemon=True).start()

        return _ok_response(
            {
                "run": replay_run,
                "replay": {
                    "accepted": True,
                    "mode": "checkpoint_replay",
                    "checkpoint_id": selected_checkpoint_id,
                    "source_run_id": run_id,
                },
            }
        )

    def fork_run(
        self,
        run_id: str,
        *,
        run_store=None,
        checkpoint_manager=None,
        checkpoint_id: str | None = None,
    ) -> dict[str, Any]:
        if run_store is None:
            return _error_response(RuntimeError("RunStore not configured"))
        if checkpoint_manager is None:
            return _error_response(RuntimeError("CheckpointManager not configured"))

        source_run = run_store.get_run(run_id)
        if source_run is None:
            return _error_response(RunNotFoundError(f"Run '{run_id}' not found"))

        selected_checkpoint_id = checkpoint_id or source_run.get("checkpoint_head")
        if not isinstance(selected_checkpoint_id, str) or not selected_checkpoint_id:
            return _error_response(
                ValueError(f"Run '{run_id}' has no checkpoint to fork from")
            )

        checkpoint = checkpoint_manager.load_checkpoint(
            run_id=run_id,
            checkpoint_id=selected_checkpoint_id,
        )
        if checkpoint is None:
            return _error_response(
                CheckpointNotFoundError(
                    f"Checkpoint '{selected_checkpoint_id}' not found for run '{run_id}'"
                )
            )

        restored_state = checkpoint_manager.load_state(
            run_id=run_id,
            checkpoint_id=selected_checkpoint_id,
        )
        if restored_state is None:
            return _error_response(
                CheckpointNotFoundError(
                    f"Checkpoint state '{selected_checkpoint_id}' not found for run '{run_id}'"
                )
            )

        source_skill_id = source_run.get("skill_id")
        if not isinstance(source_skill_id, str) or not source_skill_id:
            return _error_response(
                RuntimeError(f"Run '{run_id}' is missing skill metadata for fork")
            )

        from uuid import uuid4

        source_trace_id = (
            source_run.get("trace_id")
            if isinstance(source_run.get("trace_id"), str)
            else restored_state.trace_id
        )
        fork_run_id = f"fork_{run_id}_{uuid4().hex[:12]}"
        fork_run = run_store.fork_run(
            fork_run_id,
            skill_id=source_skill_id,
            trace_id=source_trace_id,
            source_run_id=run_id,
            source_checkpoint_id=selected_checkpoint_id,
            checkpoint_head=selected_checkpoint_id,
            metadata={
                "inputs": dict(restored_state.inputs),
                "execution_channel": (
                    source_run.get("execution_channel")
                    if isinstance(source_run.get("execution_channel"), str)
                    else "http-fork"
                ),
                "confirmed_capabilities": (
                    list((source_run.get("metadata") or {}).get("confirmed_capabilities", []))
                    if isinstance(source_run.get("metadata"), dict)
                    else []
                ),
            },
        )

        return _ok_response(
            {
                "run": fork_run,
                "fork": {
                    "accepted": True,
                    "mode": "checkpoint_fork",
                    "checkpoint_id": selected_checkpoint_id,
                    "source_run_id": run_id,
                },
            }
        )

    def list_runs(
        self,
        *,
        run_store=None,
        limit: int = 100,
        offset: int = 0,
        status: str | None = None,
    ) -> dict[str, Any]:
        if run_store is None:
            return _error_response(RuntimeError("RunStore not configured"))
        runs = run_store.list_runs_page(limit=limit, offset=offset, status=status)
        total = run_store.count_runs(status=status)
        has_more = (offset + len(runs)) < total
        response: dict[str, Any] = {
            "runs": runs,
            "pagination": {
                "offset": offset,
                "limit": limit,
                "total": total,
                "has_more": has_more,
            },
        }
        if has_more:
            response["pagination"]["next_offset"] = offset + len(runs)
        if status is not None:
            response["status"] = status
        return response

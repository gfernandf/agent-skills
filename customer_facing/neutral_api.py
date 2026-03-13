from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from runtime.engine_factory import RuntimeComponents, build_runtime_components
from runtime.models import ExecutionOptions, ExecutionRequest


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
            "timestamp": datetime.utcnow().isoformat() + "Z",
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
            if isinstance(s, dict) and rank.get(str(s.get("lifecycle_state")), -1) >= min_rank
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
        skill = self.components.skill_loader.get_skill(skill_id)
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
    ) -> dict[str, Any]:
        request = ExecutionRequest(
            skill_id=skill_id,
            inputs=inputs or {},
            options=ExecutionOptions(required_conformance_profile=required_conformance_profile),
            trace_id=trace_id,
        )
        result = self.components.engine.execute(request)

        payload: dict[str, Any] = {
            "skill_id": result.skill_id,
            "status": result.status,
            "outputs": result.outputs,
            "trace_id": result.state.trace_id,
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

        return payload

    def execute_capability(
        self,
        capability_id: str,
        inputs: dict[str, Any] | None,
        *,
        trace_id: str | None = None,
        required_conformance_profile: str | None = None,
    ) -> dict[str, Any]:
        capability = self.components.capability_loader.get_capability(capability_id)
        result = self.components.capability_executor.execute(
            capability,
            inputs or {},
            trace_id=trace_id,
            required_conformance_profile=required_conformance_profile,
        )

        if isinstance(result, tuple):
            outputs, meta = result
        else:
            outputs, meta = result, {}

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
        capability = self.components.capability_loader.get_capability(capability_id)
        executor = self.components.capability_executor.binding_executor
        return executor.build_resolution_plan(
            capability=capability,
            required_conformance_profile=required_conformance_profile,
        )

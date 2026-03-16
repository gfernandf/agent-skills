from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from customer_facing.neutral_api import NeutralRuntimeAPI
from gateway.attach_targets import AttachTargetResolver
from gateway.discovery import DiscoveryQuery, rank_skills
from gateway.evidence import DiscoveryEvidenceCache
from gateway.models import AttachResult, DiscoverResult, SkillSummary
from runtime.engine_factory import RuntimeComponents, build_runtime_components
from runtime.errors import AttachValidationError


_ALLOWED_ATTACH_TARGET_TYPES = {"task", "run", "output", "transcript", "artifact"}


class SkillGateway:
    """Agent-facing gateway for discovery and listing over existing runtime components."""

    def __init__(
        self,
        registry_root: Path,
        runtime_root: Path,
        host_root: Path,
        *,
        local_skills_root: Path | None = None,
    ) -> None:
        self.registry_root = registry_root
        self.runtime_root = runtime_root
        self.host_root = host_root
        self.components: RuntimeComponents = build_runtime_components(
            registry_root=registry_root,
            runtime_root=runtime_root,
            host_root=host_root,
            local_skills_root=local_skills_root,
        )
        self.attach_target_resolver = AttachTargetResolver(runtime_root)
        self.discovery_evidence_cache = DiscoveryEvidenceCache(runtime_root)
        self._pid = os.getpid()
        self._started_monotonic = time.monotonic()
        self._started_at_utc = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        self._persist_enabled = True
        self._state_path = self.runtime_root / "artifacts" / "gateway_diagnostics_state.json"
        self._loaded_from_disk = False
        self._last_loaded_at_utc: str | None = None
        self._last_persisted_at_utc: str | None = None
        self._operation_counts: dict[str, int] = {
            "discover": 0,
            "list": 0,
            "attach": 0,
            "diagnostics": 0,
            "reset_metrics": 0,
        }
        self._load_persisted_diagnostics_state()
        self.api = NeutralRuntimeAPI(
            registry_root=registry_root,
            runtime_root=runtime_root,
            host_root=host_root,
        )

    def discover(
        self,
        *,
        intent: str,
        domain: str | None = None,
        role_filter: str | None = None,
        limit: int = 10,
    ) -> list[DiscoverResult]:
        self._operation_counts["discover"] += 1
        summaries = self.list_skills(domain=domain)
        query = DiscoveryQuery(
            intent=intent,
            domain=domain,
            role_filter=role_filter,
            limit=limit,
        )
        return rank_skills(
            summaries,
            query,
            evidence=self.discovery_evidence_cache.get(),
        )

    def attach(
        self,
        *,
        skill_id: str,
        target_type: str,
        target_ref: str,
        inputs: dict[str, Any] | None = None,
        trace_id: str | None = None,
        include_trace: bool = False,
        required_conformance_profile: str | None = None,
        audit_mode: str | None = None,
    ) -> AttachResult:
        self._operation_counts["attach"] += 1
        if target_type not in _ALLOWED_ATTACH_TARGET_TYPES:
            raise AttachValidationError(
                "target_type must be one of "
                f"{sorted(_ALLOWED_ATTACH_TARGET_TYPES)}, got '{target_type}'"
            )

        if not isinstance(target_ref, str) or not target_ref:
            raise AttachValidationError("target_ref must be a non-empty string")

        spec = self.components.skill_loader.get_skill(skill_id)
        metadata = spec.metadata if isinstance(spec.metadata, dict) else {}
        classification = metadata.get("classification")

        if not isinstance(classification, dict):
            raise AttachValidationError(
                f"Skill '{skill_id}' is not attachable: metadata.classification is missing",
                skill_id=skill_id,
            )

        invocation = classification.get("invocation")
        if invocation not in {"attach", "both"}:
            raise AttachValidationError(
                f"Skill '{skill_id}' is not attachable: invocation='{invocation}'",
                skill_id=skill_id,
            )

        attach_targets = classification.get("attach_targets")
        if not isinstance(attach_targets, list) or not attach_targets:
            raise AttachValidationError(
                f"Skill '{skill_id}' is not attachable: attach_targets is empty",
                skill_id=skill_id,
            )

        if target_type not in {t for t in attach_targets if isinstance(t, str)}:
            raise AttachValidationError(
                f"Skill '{skill_id}' does not support attach target '{target_type}'. "
                f"Allowed targets: {sorted([t for t in attach_targets if isinstance(t, str)])}",
                skill_id=skill_id,
            )

        target_ok, reason, target_context = self.attach_target_resolver.validate(
            target_type=target_type,
            target_ref=target_ref,
        )
        if not target_ok:
            raise AttachValidationError(
                f"Invalid attach target: {reason}",
                skill_id=skill_id,
            )

        execution = self.api.execute_skill(
            skill_id=skill_id,
            inputs=inputs or {},
            trace_id=trace_id,
            include_trace=include_trace,
            required_conformance_profile=required_conformance_profile,
            audit_mode=audit_mode,
            execution_channel=f"attach:{target_type}",
        )

        result = AttachResult.now(
            skill_id=skill_id,
            target_type=target_type,
            target_ref=target_ref,
            execution=execution,
            attach_context=target_context,
        )
        self._persist_diagnostics_state()
        return result

    def list_skills(
        self,
        *,
        domain: str | None = None,
        role: str | None = None,
        status: str | None = None,
        invocation: str | None = None,
    ) -> list[SkillSummary]:
        self._operation_counts["list"] += 1
        items: list[SkillSummary] = []

        for skill_id in self._iter_skill_ids():
            spec = self.components.skill_loader.get_skill(skill_id)
            metadata = spec.metadata if isinstance(spec.metadata, dict) else {}
            classification = metadata.get("classification") if isinstance(metadata.get("classification"), dict) else {}

            summary = SkillSummary(
                skill_id=spec.id,
                name=spec.name,
                description=spec.description,
                domain=spec.domain,
                channel=spec.channel,
                status=(metadata.get("status") if isinstance(metadata.get("status"), str) else "unspecified"),
                role=(classification.get("role") if isinstance(classification.get("role"), str) else None),
                invocation=(classification.get("invocation") if isinstance(classification.get("invocation"), str) else None),
                effect_mode=(classification.get("effect_mode") if isinstance(classification.get("effect_mode"), str) else None),
                tags=tuple(str(t) for t in metadata.get("tags", []) if isinstance(t, str)),
            )

            if domain and summary.domain != domain:
                continue
            if role and summary.role != role:
                continue
            if status and summary.status != status:
                continue
            if invocation and summary.invocation != invocation:
                continue

            items.append(summary)

        items.sort(key=lambda s: s.skill_id)
        self._persist_diagnostics_state()
        return items

    def _iter_skill_ids(self) -> list[str]:
        loader = self.components.skill_loader

        list_method = getattr(loader, "list_all_ids", None)
        if callable(list_method):
            ids = list_method()
            if ids:
                return ids

            # Fallback for lazy-index loaders wrapped by CompositeSkillLoader.
            nested_loaders = getattr(loader, "_loaders", None)
            if isinstance(nested_loaders, list):
                seen: set[str] = set()
                merged: list[str] = []
                for nested in nested_loaders:
                    build_index = getattr(nested, "_build_skill_index", None)
                    if callable(build_index):
                        index = build_index()
                        if isinstance(index, dict):
                            for skill_id in index.keys():
                                if skill_id not in seen:
                                    seen.add(skill_id)
                                    merged.append(skill_id)
                if merged:
                    return merged

        index_builder = getattr(loader, "_build_skill_index", None)
        if callable(index_builder):
            index = index_builder()
            if isinstance(index, dict):
                return list(index.keys())

        return []

    def health(self) -> dict[str, Any]:
        return self.api.health()

    def diagnostics(self) -> dict[str, Any]:
        self._operation_counts["diagnostics"] += 1
        uptime_seconds = round(max(0.0, time.monotonic() - self._started_monotonic), 3)
        operation_counts = dict(self._operation_counts)
        payload = {
            "gateway": {
                "process": {
                    "pid": self._pid,
                    "started_at_utc": self._started_at_utc,
                    "uptime_seconds": uptime_seconds,
                    "operation_counts": operation_counts,
                },
                "cache": {
                    "discovery_evidence": self.discovery_evidence_cache.stats(),
                    "attach_targets": self.attach_target_resolver.cache_stats(),
                },
                "persistence": {
                    "enabled": self._persist_enabled,
                    "state_path": self._state_path.as_posix(),
                    "loaded_from_disk": self._loaded_from_disk,
                    "last_loaded_at_utc": self._last_loaded_at_utc,
                    "last_persisted_at_utc": self._last_persisted_at_utc,
                }
            }
        }
        self._persist_diagnostics_state()
        return payload

    def reset_diagnostics_metrics(self, *, clear_cache: bool = False) -> dict[str, Any]:
        self.discovery_evidence_cache.reset_metrics(clear_cache=clear_cache)
        self.attach_target_resolver.reset_metrics(clear_cache=clear_cache)
        self._operation_counts = {
            "discover": 0,
            "list": 0,
            "attach": 0,
            "diagnostics": 0,
            "reset_metrics": 1,
        }
        payload = self.diagnostics()
        payload["gateway"]["reset"] = {
            "ok": True,
            "clear_cache": clear_cache,
        }
        return payload

    def _load_persisted_diagnostics_state(self) -> None:
        if not self._persist_enabled:
            return
        if not self._state_path.exists():
            return

        try:
            raw = json.loads(self._state_path.read_text(encoding="utf-8"))
        except Exception:
            return

        if not isinstance(raw, dict):
            return

        operation_counts = raw.get("operation_counts")
        if isinstance(operation_counts, dict):
            for key in self._operation_counts:
                self._operation_counts[key] = int(operation_counts.get(key, 0))

        discovery_metrics = raw.get("discovery_evidence_metrics")
        if isinstance(discovery_metrics, dict):
            self.discovery_evidence_cache.load_metrics_snapshot(discovery_metrics)

        attach_metrics = raw.get("attach_target_metrics")
        if isinstance(attach_metrics, dict):
            self.attach_target_resolver.load_metrics_snapshot(attach_metrics)

        self._loaded_from_disk = True
        self._last_loaded_at_utc = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def _persist_diagnostics_state(self) -> None:
        if not self._persist_enabled:
            return

        payload = {
            "schema_version": "1.0",
            "updated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "operation_counts": dict(self._operation_counts),
            "discovery_evidence_metrics": self.discovery_evidence_cache.metrics_snapshot(),
            "attach_target_metrics": self.attach_target_resolver.metrics_snapshot(),
        }

        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self._state_path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        tmp_path.replace(self._state_path)
        self._last_persisted_at_utc = payload["updated_at_utc"]

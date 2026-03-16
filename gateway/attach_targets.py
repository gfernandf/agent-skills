from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class AttachTargetResolver:
    """Resolves whether a target_ref exists for a given attach target type."""

    def __init__(self, runtime_root: Path) -> None:
        self.runtime_root = runtime_root
        self._index_cache: dict[str, set[str]] | None = None
        self._index_stamp: int | None = None
        self._trace_ids_cache: set[str] | None = None
        self._trace_stamp: int | None = None
        self._task_ids_cache: set[str] | None = None
        self._task_stamp: int | None = None
        self._cache_metrics: dict[str, dict[str, int]] = {
            "formal_index": {"hits": 0, "misses": 0, "reloads": 0, "invalidations": 0},
            "runtime_audit": {"hits": 0, "misses": 0, "reloads": 0, "invalidations": 0},
            "task_registry": {"hits": 0, "misses": 0, "reloads": 0, "invalidations": 0},
        }

    def validate(self, *, target_type: str, target_ref: str) -> tuple[bool, str, dict[str, Any]]:
        index = self._load_formal_index()
        bucket = index.get(target_type)
        context: dict[str, Any] = {
            "target_type": target_type,
            "target_ref": target_ref,
        }

        # Prefer formal typed index when available for deterministic attach semantics.
        if bucket is not None and len(bucket) > 0:
            context.update(
                {
                    "validation_source": "formal_index",
                    "index_path": "artifacts/attach_targets/index.json",
                    "index_bucket": target_type,
                    "index_bucket_size": len(bucket),
                }
            )
            if target_ref in bucket:
                context["validation_result"] = "indexed_match"
                return True, "ok", context

            # For artifact targets keep pragmatic support for direct existing paths.
            if target_type == "artifact":
                p = Path(target_ref)
                if p.exists():
                    context["validation_result"] = "artifact_path_match"
                    return True, "ok", context
                rel = (self.runtime_root / target_ref).resolve()
                if rel.exists() and rel.is_file():
                    context["validation_result"] = "artifact_runtime_relative_match"
                    return True, "ok", context

            context["validation_result"] = "index_miss"
            return False, (
                f"target_ref '{target_ref}' is not present in attach target index bucket '{target_type}'. "
                "Regenerate index with tooling/build_attach_target_index.py or provide a valid indexed target_ref."
            ), context

        # Backward-compatible fallback when index is missing or bucket is empty.
        if target_type in {"run", "output", "transcript"}:
            traces = self._load_trace_ids()
            context.update(
                {
                    "validation_source": "runtime_audit",
                    "audit_path": "artifacts/runtime_skill_audit.jsonl",
                    "audit_trace_count": len(traces),
                }
            )
            if target_ref in traces:
                context["validation_result"] = "trace_match"
                return True, "ok", context
            context["validation_result"] = "trace_miss"
            return False, (
                f"target_ref '{target_ref}' was not found in runtime audit trace ids. "
                "Run the target workflow first or provide a valid existing trace_id."
            ), context

        if target_type == "artifact":
            context["validation_source"] = "artifact_or_audit_fallback"
            p = Path(target_ref)
            if p.exists():
                context["validation_result"] = "artifact_path_match"
                return True, "ok", context

            rel = (self.runtime_root / target_ref).resolve()
            if rel.exists() and rel.is_file():
                context["validation_result"] = "artifact_runtime_relative_match"
                return True, "ok", context

            traces = self._load_trace_ids()
            context["audit_trace_count"] = len(traces)
            if target_ref in traces:
                context["validation_result"] = "trace_match"
                return True, "ok", context

            context["validation_result"] = "artifact_and_trace_miss"
            return False, (
                f"target_ref '{target_ref}' was not found as file path or trace_id. "
                "Provide an existing artifact file path or known trace_id."
            ), context

        if target_type == "task":
            task_ids = self._load_task_ids()
            context.update(
                {
                    "validation_source": "task_registry",
                    "tasks_path": "artifacts/attach_targets/tasks.json",
                    "task_count": len(task_ids),
                }
            )
            if target_ref in task_ids:
                context["validation_result"] = "task_registry_match"
                return True, "ok", context
            if target_ref.startswith("task:") and len(target_ref) > len("task:"):
                context["validation_result"] = "task_prefix_match"
                return True, "ok", context
            context["validation_result"] = "task_miss"
            return False, (
                f"target_ref '{target_ref}' is not a known task id. "
                "Use task:<id> or register ids in artifacts/attach_targets/tasks.json"
            ), context

        context["validation_source"] = "unsupported_target_type"
        context["validation_result"] = "unsupported"
        return False, f"unsupported target_type '{target_type}'", context

    def _load_formal_index(self) -> dict[str, set[str]]:
        index_path = self.runtime_root / "artifacts" / "attach_targets" / "index.json"
        stamp = _mtime_ns_or_none(index_path)
        if self._index_cache is not None and self._index_stamp == stamp:
            self._cache_metrics["formal_index"]["hits"] += 1
            return self._index_cache

        self._cache_metrics["formal_index"]["misses"] += 1
        if self._index_cache is not None and self._index_stamp != stamp:
            self._cache_metrics["formal_index"]["invalidations"] += 1
        self._cache_metrics["formal_index"]["reloads"] += 1

        result: dict[str, set[str]] = {}
        if not index_path.exists():
            self._index_cache = result
            self._index_stamp = stamp
            return result

        try:
            raw: Any = json.loads(index_path.read_text(encoding="utf-8"))
        except Exception:
            self._index_cache = result
            self._index_stamp = stamp
            return result

        targets = raw.get("targets") if isinstance(raw, dict) else None
        if not isinstance(targets, dict):
            self._index_cache = result
            self._index_stamp = stamp
            return result

        for target_type, values in targets.items():
            if not isinstance(target_type, str):
                continue
            if not isinstance(values, list):
                continue
            result[target_type] = {
                v for v in values if isinstance(v, str) and v
            }

        self._index_cache = result
        self._index_stamp = stamp
        return result

    def _load_trace_ids(self) -> set[str]:
        audit_file = self.runtime_root / "artifacts" / "runtime_skill_audit.jsonl"
        stamp = _mtime_ns_or_none(audit_file)
        if self._trace_ids_cache is not None and self._trace_stamp == stamp:
            self._cache_metrics["runtime_audit"]["hits"] += 1
            return self._trace_ids_cache

        self._cache_metrics["runtime_audit"]["misses"] += 1
        if self._trace_ids_cache is not None and self._trace_stamp != stamp:
            self._cache_metrics["runtime_audit"]["invalidations"] += 1
        self._cache_metrics["runtime_audit"]["reloads"] += 1

        trace_ids: set[str] = set()
        if not audit_file.exists():
            self._trace_ids_cache = trace_ids
            self._trace_stamp = stamp
            return trace_ids

        try:
            with audit_file.open("r", encoding="utf-8") as f:
                for line in f:
                    raw = line.strip()
                    if not raw:
                        continue
                    try:
                        item = json.loads(raw)
                    except Exception:
                        continue
                    if not isinstance(item, dict):
                        continue
                    trace_id = item.get("trace_id")
                    if isinstance(trace_id, str) and trace_id:
                        trace_ids.add(trace_id)
        except Exception:
            pass

        self._trace_ids_cache = trace_ids
        self._trace_stamp = stamp
        return trace_ids

    def _load_task_ids(self) -> set[str]:
        tasks_file = self.runtime_root / "artifacts" / "attach_targets" / "tasks.json"
        stamp = _mtime_ns_or_none(tasks_file)
        if self._task_ids_cache is not None and self._task_stamp == stamp:
            self._cache_metrics["task_registry"]["hits"] += 1
            return self._task_ids_cache

        self._cache_metrics["task_registry"]["misses"] += 1
        if self._task_ids_cache is not None and self._task_stamp != stamp:
            self._cache_metrics["task_registry"]["invalidations"] += 1
        self._cache_metrics["task_registry"]["reloads"] += 1

        task_ids: set[str] = set()
        if tasks_file.exists():
            try:
                raw: Any = json.loads(tasks_file.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    candidates = raw.get("task_ids")
                    if isinstance(candidates, list):
                        for item in candidates:
                            if isinstance(item, str) and item:
                                task_ids.add(item)
                elif isinstance(raw, list):
                    for item in raw:
                        if isinstance(item, str) and item:
                            task_ids.add(item)
            except Exception:
                pass

        self._task_ids_cache = task_ids
        self._task_stamp = stamp
        return task_ids

    def cache_stats(self) -> dict[str, Any]:
        return {
            "formal_index": {
                **self._cache_metrics["formal_index"],
                "mtime_ns": self._index_stamp,
                "bucket_count": len(self._index_cache) if isinstance(self._index_cache, dict) else 0,
            },
            "runtime_audit": {
                **self._cache_metrics["runtime_audit"],
                "mtime_ns": self._trace_stamp,
                "trace_count": len(self._trace_ids_cache) if isinstance(self._trace_ids_cache, set) else 0,
            },
            "task_registry": {
                **self._cache_metrics["task_registry"],
                "mtime_ns": self._task_stamp,
                "task_count": len(self._task_ids_cache) if isinstance(self._task_ids_cache, set) else 0,
            },
        }

    def reset_metrics(self, *, clear_cache: bool = False) -> None:
        self._cache_metrics = {
            "formal_index": {"hits": 0, "misses": 0, "reloads": 0, "invalidations": 0},
            "runtime_audit": {"hits": 0, "misses": 0, "reloads": 0, "invalidations": 0},
            "task_registry": {"hits": 0, "misses": 0, "reloads": 0, "invalidations": 0},
        }
        if clear_cache:
            self._index_cache = None
            self._index_stamp = None
            self._trace_ids_cache = None
            self._trace_stamp = None
            self._task_ids_cache = None
            self._task_stamp = None

    def metrics_snapshot(self) -> dict[str, dict[str, int]]:
        return {
            "formal_index": dict(self._cache_metrics.get("formal_index", {})),
            "runtime_audit": dict(self._cache_metrics.get("runtime_audit", {})),
            "task_registry": dict(self._cache_metrics.get("task_registry", {})),
        }

    def load_metrics_snapshot(self, payload: dict[str, Any]) -> None:
        default_bucket = {"hits": 0, "misses": 0, "reloads": 0, "invalidations": 0}
        loaded: dict[str, dict[str, int]] = {}
        for name in ("formal_index", "runtime_audit", "task_registry"):
            raw = payload.get(name) if isinstance(payload, dict) else None
            if not isinstance(raw, dict):
                loaded[name] = dict(default_bucket)
                continue
            loaded[name] = {
                "hits": int(raw.get("hits", 0)),
                "misses": int(raw.get("misses", 0)),
                "reloads": int(raw.get("reloads", 0)),
                "invalidations": int(raw.get("invalidations", 0)),
            }
        self._cache_metrics = loaded


def _mtime_ns_or_none(path: Path) -> int | None:
    try:
        return path.stat().st_mtime_ns
    except OSError:
        return None

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_discovery_evidence(
    runtime_root: Path,
) -> dict[str, dict[str, float | str | None]]:
    """Load lightweight evidence signals from runtime artifacts for ranking."""
    evidence: dict[str, dict[str, float | str | None]] = {}

    usage_path = runtime_root / "artifacts" / "skill_usage_30d.json"
    quality_path = runtime_root / "artifacts" / "skill_quality.json"

    if usage_path.exists():
        try:
            usage_raw: Any = json.loads(usage_path.read_text(encoding="utf-8"))
            skills = usage_raw.get("skills") if isinstance(usage_raw, dict) else None
            if isinstance(skills, dict):
                for skill_id, item in skills.items():
                    if not isinstance(skill_id, str) or not isinstance(item, dict):
                        continue
                    slot = evidence.setdefault(skill_id, {})
                    exec_30d = item.get("executions_30d")
                    succ_30d = item.get("successes_30d")
                    p95 = item.get("p95_duration_ms")
                    slot["executions_30d"] = (
                        float(exec_30d) if isinstance(exec_30d, (int, float)) else 0.0
                    )
                    slot["successes_30d"] = (
                        float(succ_30d) if isinstance(succ_30d, (int, float)) else 0.0
                    )
                    slot["p95_duration_ms"] = (
                        float(p95) if isinstance(p95, (int, float)) else None
                    )
        except Exception:
            pass

    if quality_path.exists():
        try:
            quality_raw: Any = json.loads(quality_path.read_text(encoding="utf-8"))
            skills = (
                quality_raw.get("skills") if isinstance(quality_raw, dict) else None
            )
            if isinstance(skills, list):
                for item in skills:
                    if not isinstance(item, dict):
                        continue
                    skill_id = item.get("skill_id")
                    if not isinstance(skill_id, str) or not skill_id:
                        continue
                    slot = evidence.setdefault(skill_id, {})
                    overall = item.get("overall_score")
                    lifecycle = item.get("lifecycle_state")
                    slot["overall_score"] = (
                        float(overall) if isinstance(overall, (int, float)) else None
                    )
                    slot["lifecycle_state"] = (
                        lifecycle if isinstance(lifecycle, str) else None
                    )
        except Exception:
            pass

    return evidence


class DiscoveryEvidenceCache:
    """Caches discovery evidence and invalidates it when artifact mtimes change."""

    def __init__(self, runtime_root: Path) -> None:
        self.runtime_root = runtime_root
        self._cached: dict[str, dict[str, float | str | None]] | None = None
        self._stamp: tuple[int | None, int | None] | None = None
        self._hits = 0
        self._misses = 0
        self._reloads = 0
        self._invalidations = 0

    def get(self) -> dict[str, dict[str, float | str | None]]:
        stamp = self._compute_stamp()
        if self._cached is None or self._stamp != stamp:
            self._misses += 1
            if (
                self._cached is not None
                and self._stamp is not None
                and self._stamp != stamp
            ):
                self._invalidations += 1
            self._cached = load_discovery_evidence(self.runtime_root)
            self._stamp = stamp
            self._reloads += 1
        else:
            self._hits += 1
        return self._cached

    def invalidate(self) -> None:
        self._cached = None
        self._stamp = None
        self._invalidations += 1

    def stats(self) -> dict[str, int | tuple[int | None, int | None] | None]:
        return {
            "hits": self._hits,
            "misses": self._misses,
            "reloads": self._reloads,
            "invalidations": self._invalidations,
            "current_stamp": self._stamp,
            "cached_entries": len(self._cached)
            if isinstance(self._cached, dict)
            else 0,
        }

    def reset_metrics(self, *, clear_cache: bool = False) -> None:
        self._hits = 0
        self._misses = 0
        self._reloads = 0
        self._invalidations = 0
        if clear_cache:
            self._cached = None
            self._stamp = None

    def metrics_snapshot(self) -> dict[str, int]:
        return {
            "hits": self._hits,
            "misses": self._misses,
            "reloads": self._reloads,
            "invalidations": self._invalidations,
        }

    def load_metrics_snapshot(self, payload: dict[str, Any]) -> None:
        self._hits = int(payload.get("hits", 0)) if isinstance(payload, dict) else 0
        self._misses = int(payload.get("misses", 0)) if isinstance(payload, dict) else 0
        self._reloads = (
            int(payload.get("reloads", 0)) if isinstance(payload, dict) else 0
        )
        self._invalidations = (
            int(payload.get("invalidations", 0)) if isinstance(payload, dict) else 0
        )

    def _compute_stamp(self) -> tuple[int | None, int | None]:
        usage = self.runtime_root / "artifacts" / "skill_usage_30d.json"
        quality = self.runtime_root / "artifacts" / "skill_quality.json"
        return (
            _mtime_ns_or_none(usage),
            _mtime_ns_or_none(quality),
        )


def _mtime_ns_or_none(path: Path) -> int | None:
    try:
        return path.stat().st_mtime_ns
    except OSError:
        return None

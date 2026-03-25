"""In-memory run store for async execution tracking.

Stores run metadata in a thread-safe dict.  Optionally persists completed
runs to a JSONL file for post-mortem analysis.

This is NOT a replacement for the audit system — it tracks async run
lifecycle for the HTTP client.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class RunStore:
    """Thread-safe in-memory run store with optional JSONL persistence."""

    def __init__(self, *, persist_path: Path | None = None, max_runs: int = 100) -> None:
        self._lock = threading.Lock()
        self._runs: dict[str, dict[str, Any]] = {}
        self._order: list[str] = []
        self._max_runs = max(1, max_runs)
        self._persist_path = persist_path

    def create_run(
        self,
        run_id: str,
        skill_id: str,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        run = {
            "run_id": run_id,
            "skill_id": skill_id,
            "status": "running",
            "trace_id": trace_id,
            "created_at": _utc_now_iso(),
            "finished_at": None,
            "result": None,
            "error": None,
        }
        with self._lock:
            self._runs[run_id] = run
            self._order.append(run_id)
            self._evict()
        return run

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            run = self._runs.get(run_id)
            return dict(run) if run else None

    def list_runs(self, *, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            ids = self._order[-limit:]
            return [dict(self._runs[rid]) for rid in reversed(ids) if rid in self._runs]

    def complete_run(self, run_id: str, result: dict[str, Any]) -> None:
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                return
            run["status"] = "completed"
            run["finished_at"] = _utc_now_iso()
            run["result"] = result
        self._persist(run_id)

    def fail_run(self, run_id: str, error: str) -> None:
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                return
            run["status"] = "failed"
            run["finished_at"] = _utc_now_iso()
            run["error"] = error
        self._persist(run_id)

    # ── Internal ─────────────────────────────────────────────────────────

    def _evict(self) -> None:
        """Remove oldest runs when exceeding max_runs.  Caller holds lock."""
        while len(self._order) > self._max_runs:
            oldest = self._order.pop(0)
            self._runs.pop(oldest, None)

    def _persist(self, run_id: str) -> None:
        if self._persist_path is None:
            return
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                return
            snapshot = dict(run)
        try:
            self._persist_path.parent.mkdir(parents=True, exist_ok=True)
            with self._persist_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(snapshot, ensure_ascii=False, default=str) + "\n")
        except Exception:
            pass  # persistence is best-effort


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

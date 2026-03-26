"""In-memory run store for async execution tracking.

Stores run metadata in a thread-safe dict.  Optionally persists completed
runs to a JSONL file for post-mortem analysis.

Supports pluggable backends via the RunStoreBackend protocol for production
deployments (PostgreSQL, Redis, etc.).

This is NOT a replacement for the audit system — it tracks async run
lifecycle for the HTTP client.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


# ── Pluggable backend protocol ────────────────────────────────────


@runtime_checkable
class RunStoreBackend(Protocol):
    """Interface for persistent run store backends.

    Implement this protocol to back the RunStore with PostgreSQL, Redis,
    or any other persistent storage. The default in-memory backend is used
    when no external backend is provided.

    Example PostgreSQL implementation::

        class PostgresRunStoreBackend:
            def __init__(self, dsn: str): ...
            def save_run(self, run: dict[str, Any]) -> None: ...
            def load_run(self, run_id: str) -> dict[str, Any] | None: ...
            def list_runs(self, *, limit: int = 100) -> list[dict[str, Any]]: ...
            def delete_run(self, run_id: str) -> bool: ...
    """

    def save_run(self, run: dict[str, Any]) -> None: ...
    def load_run(self, run_id: str) -> dict[str, Any] | None: ...
    def list_runs(self, *, limit: int = 100) -> list[dict[str, Any]]: ...
    def delete_run(self, run_id: str) -> bool: ...


class RunStore:
    """Thread-safe in-memory run store with optional JSONL persistence."""

    def __init__(
        self,
        *,
        persist_path: Path | None = None,
        max_runs: int = 100,
        backend: RunStoreBackend | None = None,
    ) -> None:
        self._lock = threading.Lock()
        self._runs: dict[str, dict[str, Any]] = {}
        self._order: list[str] = []
        self._max_runs = max(1, max_runs)
        self._persist_path = persist_path
        self._backend = backend

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
        if self._backend is not None:
            try:
                self._backend.save_run(run)
            except Exception:
                pass  # backend persistence is best-effort
        return run

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            run = self._runs.get(run_id)
            if run is not None:
                return dict(run)
        # Fallback to backend if not in memory
        if self._backend is not None:
            try:
                return self._backend.load_run(run_id)
            except Exception:
                pass
        return None

    def list_runs(self, *, limit: int = 100) -> list[dict[str, Any]]:
        # Prefer backend if available (has full history)
        if self._backend is not None:
            try:
                return self._backend.list_runs(limit=limit)
            except Exception:
                pass
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
        if self._backend is not None:
            try:
                self._backend.save_run(dict(run))
            except Exception:
                pass

    def fail_run(self, run_id: str, error: str) -> None:
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                return
            run["status"] = "failed"
            run["finished_at"] = _utc_now_iso()
            run["error"] = error
        self._persist(run_id)
        if self._backend is not None:
            try:
                self._backend.save_run(dict(run))
            except Exception:
                pass

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

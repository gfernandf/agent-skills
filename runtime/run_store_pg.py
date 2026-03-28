"""PostgreSQL backend for RunStore.

Implements the ``RunStoreBackend`` protocol using ``psycopg2`` (or any
DB-API 2.0 compatible PostgreSQL driver).

Usage::

    from runtime.run_store_pg import PostgresRunStoreBackend
    from runtime.run_store import RunStore

    backend = PostgresRunStoreBackend("postgresql://user:pass@host/db")
    store = RunStore(backend=backend)

The backend auto-creates the ``agent_skills_runs`` table on first use.
Requires: ``psycopg2-binary`` (or ``psycopg2``).
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

_CREATE_TABLE = """\
CREATE TABLE IF NOT EXISTS agent_skills_runs (
    run_id      TEXT PRIMARY KEY,
    skill_id    TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'running',
    trace_id    TEXT,
    created_at  TEXT NOT NULL,
    finished_at TEXT,
    result      JSONB,
    error       TEXT
);
CREATE INDEX IF NOT EXISTS idx_runs_status ON agent_skills_runs (status);
CREATE INDEX IF NOT EXISTS idx_runs_created ON agent_skills_runs (created_at DESC);
"""


class PostgresRunStoreBackend:
    """RunStoreBackend implementation backed by PostgreSQL.

    Thread-safe: each method acquires its own connection from the pool
    (when using a connection pool DSN) or uses a single connection with
    autocommit mode.
    """

    def __init__(self, dsn: str, *, auto_create_table: bool = True) -> None:
        try:
            import psycopg2
        except ImportError as exc:
            raise ImportError(
                "PostgreSQL backend requires psycopg2. "
                "Install with: pip install psycopg2-binary"
            ) from exc

        self._dsn = dsn
        self._conn = psycopg2.connect(dsn)
        self._conn.autocommit = True

        if auto_create_table:
            self._ensure_table()

    def _ensure_table(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute(_CREATE_TABLE)
        logger.info("PostgreSQL run store table ensured.")

    def save_run(self, run: dict[str, Any]) -> None:
        sql = """\
            INSERT INTO agent_skills_runs
                (run_id, skill_id, status, trace_id, created_at, finished_at, result, error)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (run_id) DO UPDATE SET
                status = EXCLUDED.status,
                finished_at = EXCLUDED.finished_at,
                result = EXCLUDED.result,
                error = EXCLUDED.error
        """
        result_json = json.dumps(run.get("result")) if run.get("result") else None
        with self._conn.cursor() as cur:
            cur.execute(
                sql,
                (
                    run["run_id"],
                    run["skill_id"],
                    run["status"],
                    run.get("trace_id"),
                    run["created_at"],
                    run.get("finished_at"),
                    result_json,
                    run.get("error"),
                ),
            )

    def load_run(self, run_id: str) -> dict[str, Any] | None:
        sql = "SELECT run_id, skill_id, status, trace_id, created_at, finished_at, result, error FROM agent_skills_runs WHERE run_id = %s"
        with self._conn.cursor() as cur:
            cur.execute(sql, (run_id,))
            row = cur.fetchone()
        if row is None:
            return None
        return self._row_to_dict(row)

    def list_runs(self, *, limit: int = 100) -> list[dict[str, Any]]:
        sql = "SELECT run_id, skill_id, status, trace_id, created_at, finished_at, result, error FROM agent_skills_runs ORDER BY created_at DESC LIMIT %s"
        with self._conn.cursor() as cur:
            cur.execute(sql, (limit,))
            rows = cur.fetchall()
        return [self._row_to_dict(r) for r in rows]

    def delete_run(self, run_id: str) -> bool:
        sql = "DELETE FROM agent_skills_runs WHERE run_id = %s"
        with self._conn.cursor() as cur:
            cur.execute(sql, (run_id,))
            return cur.rowcount > 0

    def close(self) -> None:
        """Close the database connection."""
        if self._conn and not self._conn.closed:
            self._conn.close()

    @staticmethod
    def _row_to_dict(row: tuple) -> dict[str, Any]:
        result_val = row[6]
        if isinstance(result_val, str):
            try:
                result_val = json.loads(result_val)
            except json.JSONDecodeError:
                pass
        return {
            "run_id": row[0],
            "skill_id": row[1],
            "status": row[2],
            "trace_id": row[3],
            "created_at": row[4],
            "finished_at": row[5],
            "result": result_val,
            "error": row[7],
        }

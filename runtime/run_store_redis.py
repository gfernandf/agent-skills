"""Redis backend for RunStore.

Implements the ``RunStoreBackend`` protocol using ``redis-py``.

Usage::

    from runtime.run_store_redis import RedisRunStoreBackend
    from runtime.run_store import RunStore

    backend = RedisRunStoreBackend("redis://localhost:6379/0")
    store = RunStore(backend=backend)

Runs are stored as JSON strings in Redis hashes, with a sorted set
for ordering by creation time.

Requires: ``redis`` (``pip install redis``).
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

_HASH_PREFIX = "agent_skills:run:"
_INDEX_KEY = "agent_skills:runs_by_time"


class RedisRunStoreBackend:
    """RunStoreBackend implementation backed by Redis."""

    def __init__(
        self,
        url: str = "redis://localhost:6379/0",
        *,
        key_prefix: str = "agent_skills:",
        ttl_seconds: int = 86400 * 7,  # 7 days default TTL
    ) -> None:
        try:
            import redis
        except ImportError as exc:
            raise ImportError(
                "Redis backend requires redis-py. Install with: pip install redis"
            ) from exc

        self._client = redis.Redis.from_url(url, decode_responses=True)
        self._prefix = key_prefix
        self._hash_prefix = f"{key_prefix}run:"
        self._index_key = f"{key_prefix}runs_by_time"
        self._ttl = ttl_seconds

    def save_run(self, run: dict[str, Any]) -> None:
        run_id = run["run_id"]
        key = f"{self._hash_prefix}{run_id}"
        # Serialize result as JSON string for Redis
        store_val = dict(run)
        if store_val.get("result") is not None:
            store_val["result"] = json.dumps(store_val["result"])
        self._client.hset(key, mapping=store_val)
        if self._ttl > 0:
            self._client.expire(key, self._ttl)
        # Maintain sorted set for ordering (score = timestamp from created_at)
        import time

        try:
            from datetime import datetime

            dt = datetime.fromisoformat(run["created_at"].replace("Z", "+00:00"))
            score = dt.timestamp()
        except Exception:
            score = time.time()
        self._client.zadd(self._index_key, {run_id: score})

    def load_run(self, run_id: str) -> dict[str, Any] | None:
        key = f"{self._hash_prefix}{run_id}"
        data = self._client.hgetall(key)
        if not data:
            return None
        return self._deserialize(data)

    def list_runs(self, *, limit: int = 100) -> list[dict[str, Any]]:
        # Get latest run_ids from sorted set (descending)
        run_ids = self._client.zrevrange(self._index_key, 0, limit - 1)
        results = []
        for run_id in run_ids:
            run = self.load_run(run_id)
            if run:
                results.append(run)
        return results

    def delete_run(self, run_id: str) -> bool:
        key = f"{self._hash_prefix}{run_id}"
        deleted = self._client.delete(key)
        self._client.zrem(self._index_key, run_id)
        return deleted > 0

    def close(self) -> None:
        """Close the Redis connection."""
        self._client.close()

    @staticmethod
    def _deserialize(data: dict[str, str]) -> dict[str, Any]:
        result: dict[str, Any] = dict(data)
        # Deserialize JSON result field
        if "result" in result and result["result"]:
            try:
                result["result"] = json.loads(result["result"])
            except (json.JSONDecodeError, TypeError):
                pass
        elif "result" in result:
            result["result"] = None
        return result

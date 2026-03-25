"""Lightweight in-process metrics collector for runtime observability.

Counters are thread-safe and can be read via ``snapshot()`` for export to
any external monitoring system.  No external dependencies.
"""

from __future__ import annotations

import threading
import time
from typing import Any


class _Counter:
    __slots__ = ("_value", "_lock")

    def __init__(self) -> None:
        self._value: int = 0
        self._lock = threading.Lock()

    def inc(self, n: int = 1) -> None:
        with self._lock:
            self._value += n

    @property
    def value(self) -> int:
        return self._value


class _Histogram:
    """Minimal histogram — keeps count, sum, min, max for latency distributions."""

    __slots__ = ("_count", "_total", "_min", "_max", "_lock")

    def __init__(self) -> None:
        self._count: int = 0
        self._total: float = 0.0
        self._min: float = float("inf")
        self._max: float = 0.0
        self._lock = threading.Lock()

    def observe(self, value: float) -> None:
        with self._lock:
            self._count += 1
            self._total += value
            if value < self._min:
                self._min = value
            if value > self._max:
                self._max = value

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "count": self._count,
                "total": round(self._total, 3),
                "min": round(self._min, 3) if self._count else None,
                "max": round(self._max, 3) if self._count else None,
                "avg": round(self._total / self._count, 3) if self._count else None,
            }


class RuntimeMetrics:
    """Singleton-style metrics registry for the runtime."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[str, _Counter] = {}
        self._histograms: dict[str, _Histogram] = {}
        self._created_at: float = time.monotonic()

    # -- counters -----------------------------------------------------------

    def _counter(self, name: str) -> _Counter:
        with self._lock:
            if name not in self._counters:
                self._counters[name] = _Counter()
            return self._counters[name]

    def inc(self, name: str, n: int = 1) -> None:
        self._counter(name).inc(n)

    # -- histograms ---------------------------------------------------------

    def _histogram(self, name: str) -> _Histogram:
        with self._lock:
            if name not in self._histograms:
                self._histograms[name] = _Histogram()
            return self._histograms[name]

    def observe(self, name: str, value: float) -> None:
        self._histogram(name).observe(value)

    # -- export -------------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        uptime = round(time.monotonic() - self._created_at, 3)
        with self._lock:
            counters = {k: c.value for k, c in sorted(self._counters.items())}
            histograms = {k: h.snapshot() for k, h in sorted(self._histograms.items())}
        return {
            "uptime_seconds": uptime,
            "counters": counters,
            "histograms": histograms,
        }


# Module-level default instance — importable by all runtime components.
METRICS = RuntimeMetrics()

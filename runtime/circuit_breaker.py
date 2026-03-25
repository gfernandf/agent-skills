"""
Lightweight per-service circuit breaker for the binding fallback chain.

States:
  - closed:    normal operation, requests pass through
  - open:      service considered down, requests short-circuited
  - half-open: one probe request allowed to check recovery

Thread-safe: uses a lock per breaker instance.
"""

from __future__ import annotations

import threading
import time
from typing import Any


_DEFAULT_FAILURE_THRESHOLD = 5
_DEFAULT_RECOVERY_TIMEOUT_SECONDS = 30.0
_DEFAULT_HALF_OPEN_MAX_CALLS = 1


class CircuitOpenError(Exception):
    """Raised when the circuit is open and the call is rejected."""

    def __init__(self, service_id: str, remaining_seconds: float) -> None:
        super().__init__(
            f"Circuit open for service '{service_id}' — "
            f"retry in {remaining_seconds:.1f}s."
        )
        self.service_id = service_id
        self.remaining_seconds = remaining_seconds


class _CircuitState:
    __slots__ = (
        "failure_count",
        "state",
        "opened_at",
        "half_open_calls",
        "lock",
    )

    def __init__(self) -> None:
        self.failure_count: int = 0
        self.state: str = "closed"
        self.opened_at: float = 0.0
        self.half_open_calls: int = 0
        self.lock = threading.Lock()


class CircuitBreakerRegistry:
    """
    Registry of per-service circuit breakers.

    Usage:
        registry = CircuitBreakerRegistry()
        registry.before_call(service_id)   # raises CircuitOpenError if open
        try:
            result = do_call(...)
            registry.record_success(service_id)
        except Exception:
            registry.record_failure(service_id)
            raise
    """

    def __init__(
        self,
        failure_threshold: int = _DEFAULT_FAILURE_THRESHOLD,
        recovery_timeout: float = _DEFAULT_RECOVERY_TIMEOUT_SECONDS,
    ) -> None:
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._breakers: dict[str, _CircuitState] = {}
        self._global_lock = threading.Lock()

    def _get(self, service_id: str) -> _CircuitState:
        if service_id not in self._breakers:
            with self._global_lock:
                if service_id not in self._breakers:
                    self._breakers[service_id] = _CircuitState()
        return self._breakers[service_id]

    def before_call(self, service_id: str) -> None:
        cb = self._get(service_id)
        with cb.lock:
            if cb.state == "closed":
                return
            if cb.state == "open":
                elapsed = time.monotonic() - cb.opened_at
                if elapsed >= self._recovery_timeout:
                    cb.state = "half-open"
                    cb.half_open_calls = 0
                else:
                    raise CircuitOpenError(
                        service_id,
                        remaining_seconds=self._recovery_timeout - elapsed,
                    )
            # half-open: allow limited probe calls
            if cb.state == "half-open":
                if cb.half_open_calls >= _DEFAULT_HALF_OPEN_MAX_CALLS:
                    raise CircuitOpenError(
                        service_id,
                        remaining_seconds=max(
                            0.0,
                            self._recovery_timeout
                            - (time.monotonic() - cb.opened_at),
                        ),
                    )
                cb.half_open_calls += 1

    def record_success(self, service_id: str) -> None:
        cb = self._get(service_id)
        with cb.lock:
            cb.failure_count = 0
            cb.state = "closed"

    def record_failure(self, service_id: str) -> None:
        cb = self._get(service_id)
        with cb.lock:
            cb.failure_count += 1
            if cb.state == "half-open":
                cb.state = "open"
                cb.opened_at = time.monotonic()
            elif cb.failure_count >= self._failure_threshold:
                cb.state = "open"
                cb.opened_at = time.monotonic()

    def get_state(self, service_id: str) -> dict[str, Any]:
        """Diagnostic snapshot of a single breaker."""
        cb = self._get(service_id)
        with cb.lock:
            return {
                "state": cb.state,
                "failure_count": cb.failure_count,
                "opened_at": cb.opened_at,
            }

"""
Optional OpenTelemetry integration for agent-skills.

When the ``opentelemetry-api`` package is installed the module exposes real
spans; otherwise every public helper degrades gracefully to no-ops so the
rest of the runtime never needs to guard imports.
"""

from __future__ import annotations

import functools
from contextlib import contextmanager
from typing import Any, Generator

# ---------------------------------------------------------------------------
# Detect OTel availability once at import time
# ---------------------------------------------------------------------------
try:
    from opentelemetry import trace as _otel_trace  # type: ignore[import-untyped]
    from opentelemetry.trace import StatusCode as _StatusCode  # type: ignore[import-untyped]

    _HAS_OTEL = True
except ImportError:  # pragma: no cover – tested via mock
    _HAS_OTEL = False
    _otel_trace = None  # type: ignore[assignment]
    _StatusCode = None  # type: ignore[assignment]

_TRACER_NAME = "orca-agent-skills"


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def otel_available() -> bool:
    """Return ``True`` when the OTel SDK is importable."""
    return _HAS_OTEL


def get_tracer():
    """Return an OTel tracer or ``None`` when the SDK is absent."""
    if not _HAS_OTEL:
        return None
    return _otel_trace.get_tracer(_TRACER_NAME)


@contextmanager
def start_span(
    name: str,
    attributes: dict[str, Any] | None = None,
) -> Generator[Any, None, None]:
    """Context-manager that wraps ``tracer.start_as_current_span``.

    Yields the real span when OTel is present, otherwise yields a
    lightweight no-op object so callers can unconditionally call
    ``span.set_attribute()`` without guards.
    """
    if not _HAS_OTEL:
        yield _NoopSpan()
        return
    tracer = _otel_trace.get_tracer(_TRACER_NAME)
    with tracer.start_as_current_span(name, attributes=attributes or {}) as span:
        yield span


def record_exception(span: Any, exc: BaseException) -> None:
    """Record an exception on *span* if OTel is available."""
    if _HAS_OTEL and hasattr(span, "record_exception"):
        span.record_exception(exc)
        span.set_status(_StatusCode.ERROR, str(exc))


def traced(name: str | None = None, **static_attrs: Any):
    """Decorator that wraps a function in an OTel span.

    Usage::

        @traced("skill.execute")
        def execute(self, request):
            ...

    When OTel is absent the original function runs unchanged.
    """

    def decorator(fn):
        span_name = name or f"{fn.__module__}.{fn.__qualname__}"

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            if not _HAS_OTEL:
                return fn(*args, **kwargs)
            tracer = _otel_trace.get_tracer(_TRACER_NAME)
            with tracer.start_as_current_span(
                span_name, attributes=static_attrs
            ) as span:
                try:
                    result = fn(*args, **kwargs)
                    return result
                except Exception as exc:
                    record_exception(span, exc)
                    raise

        return wrapper

    return decorator


# ---------------------------------------------------------------------------
# No-op helpers (zero-cost when the SDK is not installed)
# ---------------------------------------------------------------------------


class _NoopSpan:
    """Minimal duck-typed span so callers can always call set_attribute."""

    def set_attribute(self, key: str, value: Any) -> None:  # noqa: D401
        pass

    def set_status(self, *_a: Any, **_kw: Any) -> None:
        pass

    def record_exception(self, *_a: Any, **_kw: Any) -> None:
        pass

    def add_event(self, name: str, attributes: dict | None = None) -> None:
        pass

"""
Tests for runtime.otel_integration — OpenTelemetry span helpers.

Validates that the NoOp path works when OTel is absent and
that the wrappers behave correctly with a mock tracer.

Run: python -m runtime.test_otel_integration
"""
from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

_pass = 0
_fail = 0


def _test(label: str, condition: bool, detail: str = "") -> None:
    global _pass, _fail
    if condition:
        _pass += 1
    else:
        _fail += 1
        msg = f"  FAIL: {label}"
        if detail:
            msg += f" — {detail}"
        print(msg)


# -------------------------------------------------------------------
# Tests
# -------------------------------------------------------------------

def test_otel_available_returns_bool():
    from runtime.otel_integration import otel_available
    result = otel_available()
    _test("otel_available returns bool", isinstance(result, bool))


def test_noop_span_has_set_attribute():
    from runtime.otel_integration import _NoopSpan
    span = _NoopSpan()
    # Should not raise
    span.set_attribute("key", "value")
    span.set_status("OK")
    span.record_exception(RuntimeError("test"))
    span.add_event("test_event")
    _test("NoopSpan methods callable", True)


def test_start_span_noop():
    """When OTel is not installed, start_span yields a _NoopSpan."""
    from runtime import otel_integration as mod
    original = mod._HAS_OTEL
    try:
        mod._HAS_OTEL = False
        from runtime.otel_integration import start_span, _NoopSpan
        with start_span("test.span") as span:
            _test("start_span noop yields NoopSpan", isinstance(span, _NoopSpan))
            span.set_attribute("foo", "bar")  # should not raise
    finally:
        mod._HAS_OTEL = original


def test_get_tracer_noop():
    from runtime import otel_integration as mod
    original = mod._HAS_OTEL
    try:
        mod._HAS_OTEL = False
        _test("get_tracer returns None when no OTel", mod.get_tracer() is None)
    finally:
        mod._HAS_OTEL = original


def test_record_exception_noop():
    from runtime.otel_integration import record_exception, _NoopSpan
    span = _NoopSpan()
    # Should not raise
    record_exception(span, RuntimeError("test"))
    _test("record_exception noop does not raise", True)


def test_traced_decorator_noop():
    from runtime import otel_integration as mod
    original = mod._HAS_OTEL
    try:
        mod._HAS_OTEL = False
        from runtime.otel_integration import traced
        call_count = 0

        @traced("test.operation")
        def sample():
            nonlocal call_count
            call_count += 1
            return 42

        result = sample()
        _test("traced noop returns correct value", result == 42)
        _test("traced noop called function", call_count == 1)
    finally:
        mod._HAS_OTEL = original


def test_traced_decorator_with_mock_otel():
    """When OTel is available, the decorator should create a span."""
    from runtime import otel_integration as mod
    original = mod._HAS_OTEL
    original_trace = mod._otel_trace
    try:
        mock_span = MagicMock()
        mock_tracer = MagicMock()
        mock_tracer.start_as_current_span.return_value.__enter__ = MagicMock(return_value=mock_span)
        mock_tracer.start_as_current_span.return_value.__exit__ = MagicMock(return_value=False)
        mock_trace_mod = MagicMock()
        mock_trace_mod.get_tracer.return_value = mock_tracer

        mod._HAS_OTEL = True
        mod._otel_trace = mock_trace_mod

        from runtime.otel_integration import traced

        @traced("my.span")
        def do_work():
            return "done"

        result = do_work()
        _test("traced with mock returns value", result == "done")
        _test("traced with mock called get_tracer", mock_trace_mod.get_tracer.called)
    finally:
        mod._HAS_OTEL = original
        mod._otel_trace = original_trace


def test_start_span_with_mock_otel():
    """When OTel is available, start_span delegates to the real tracer."""
    from runtime import otel_integration as mod
    original = mod._HAS_OTEL
    original_trace = mod._otel_trace
    try:
        mock_span = MagicMock()
        mock_tracer = MagicMock()
        mock_tracer.start_as_current_span.return_value.__enter__ = MagicMock(return_value=mock_span)
        mock_tracer.start_as_current_span.return_value.__exit__ = MagicMock(return_value=False)
        mock_trace_mod = MagicMock()
        mock_trace_mod.get_tracer.return_value = mock_tracer

        mod._HAS_OTEL = True
        mod._otel_trace = mock_trace_mod

        from runtime.otel_integration import start_span
        with start_span("test.span", attributes={"key": "val"}) as span:
            _test("start_span mock yields mock span", span is mock_span)
        _test("start_span mock called tracer", mock_trace_mod.get_tracer.called)
    finally:
        mod._HAS_OTEL = original
        mod._otel_trace = original_trace


# -------------------------------------------------------------------
# Runner
# -------------------------------------------------------------------

def main() -> None:
    test_otel_available_returns_bool()
    test_noop_span_has_set_attribute()
    test_start_span_noop()
    test_get_tracer_noop()
    test_record_exception_noop()
    test_traced_decorator_noop()
    test_traced_decorator_with_mock_otel()
    test_start_span_with_mock_otel()
    print(f"\notel_integration tests: {_pass} passed, {_fail} failed")
    if _fail:
        sys.exit(1)


if __name__ == "__main__":
    main()

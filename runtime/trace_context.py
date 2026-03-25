"""O2 — W3C Trace Context (traceparent / tracestate) propagation.

Implements https://www.w3.org/TR/trace-context/ for cross-service and
nested-skill trace correlation.

Usage in OpenAPI invoker::

    from runtime.trace_context import inject_traceparent, extract_traceparent

    # Outgoing request — inject header
    headers = inject_traceparent(trace_id, span_id)

    # Incoming request — extract header
    ctx = extract_traceparent(request_headers.get("traceparent"))
"""
from __future__ import annotations

import os
import re
import secrets
from dataclasses import dataclass
from typing import Any

# traceparent format: version-trace_id-parent_id-trace_flags
# Example: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
_TRACEPARENT_RE = re.compile(
    r"^([0-9a-f]{2})-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})$"
)
_VERSION = "00"
_FLAG_SAMPLED = 0x01


@dataclass(frozen=True)
class TraceContext:
    """Parsed W3C trace context."""
    trace_id: str        # 32 hex chars
    parent_id: str       # 16 hex chars
    trace_flags: int     # 8-bit flags
    tracestate: str = "" # opaque vendor state

    @property
    def sampled(self) -> bool:
        return bool(self.trace_flags & _FLAG_SAMPLED)


def generate_span_id() -> str:
    """Generate a random 16-char hex span ID."""
    return secrets.token_hex(8)


def generate_trace_id() -> str:
    """Generate a random 32-char hex trace ID."""
    return secrets.token_hex(16)


def extract_traceparent(header_value: str | None) -> TraceContext | None:
    """Parse a ``traceparent`` header.  Returns None on invalid/missing."""
    if not header_value:
        return None
    header_value = header_value.strip()
    m = _TRACEPARENT_RE.match(header_value)
    if not m:
        return None
    version, trace_id, parent_id, flags_hex = m.groups()
    # All zeros trace/parent IDs are invalid per spec
    if trace_id == "0" * 32 or parent_id == "0" * 16:
        return None
    return TraceContext(
        trace_id=trace_id,
        parent_id=parent_id,
        trace_flags=int(flags_hex, 16),
    )


def inject_traceparent(
    trace_id: str | None = None,
    parent_id: str | None = None,
    *,
    sampled: bool = True,
    tracestate: str = "",
) -> dict[str, str]:
    """Build outgoing ``traceparent`` (and optional ``tracestate``) headers.

    If *trace_id* is not a valid 32-hex string a new one is generated.
    A new *parent_id* is always generated (represents the current span).
    """
    if not trace_id or not re.fullmatch(r"[0-9a-f]{32}", trace_id):
        trace_id = generate_trace_id()
    span_id = parent_id or generate_span_id()
    flags = f"{_FLAG_SAMPLED:02x}" if sampled else "00"
    headers: dict[str, str] = {
        "traceparent": f"{_VERSION}-{trace_id}-{span_id}-{flags}",
    }
    if tracestate:
        headers["tracestate"] = tracestate
    return headers


def trace_id_from_internal(internal_trace_id: str | None) -> str:
    """Convert an internal UUID-style trace_id to a 32-hex W3C trace_id.

    If the internal ID is already 32 hex chars, return as-is.
    Otherwise strip dashes and pad/truncate to 32 chars.
    """
    if not internal_trace_id:
        return generate_trace_id()
    cleaned = internal_trace_id.replace("-", "").lower()
    if re.fullmatch(r"[0-9a-f]+", cleaned):
        return cleaned[:32].ljust(32, "0")
    # Fallback: hash the string
    import hashlib
    return hashlib.sha256(internal_trace_id.encode()).hexdigest()[:32]

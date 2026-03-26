from __future__ import annotations

import json
import logging
import os
import time
from contextvars import ContextVar, Token
from typing import Any

_LOGGER_NAME = "agent_skills"
_LOG_LEVEL = os.getenv("AGENT_SKILLS_LOG_LEVEL", "INFO").upper()
_MAX_STR_LEN = int(os.getenv("AGENT_SKILLS_LOG_MAX_STR_LEN", "512"))
_MAX_COLLECTION_ITEMS = int(os.getenv("AGENT_SKILLS_LOG_MAX_ITEMS", "50"))
_REDACTION_TOKEN = "[REDACTED]"
_SENSITIVE_KEY_PARTS = {
    "password",
    "secret",
    "token",
    "apikey",
    "api_key",
    "authorization",
    "auth",
    "cookie",
    "set-cookie",
    "key",
    "private",
    "credential",
    "session",
}
_TRACE_ID_CTX: ContextVar[str | None] = ContextVar(
    "agent_skills_trace_id", default=None
)


def _configure_logger() -> logging.Logger:
    logger = logging.getLogger(_LOGGER_NAME)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
    logger.setLevel(getattr(logging, _LOG_LEVEL, logging.INFO))
    logger.propagate = False
    return logger


_LOGGER = _configure_logger()


def _truncate_str(value: str) -> str:
    if len(value) <= _MAX_STR_LEN:
        return value
    return value[:_MAX_STR_LEN] + "...[truncated]"


def _is_sensitive_key(key: str) -> bool:
    key_lc = key.lower()
    return any(part in key_lc for part in _SENSITIVE_KEY_PARTS)


def _sanitize(value: Any, key_path: tuple[str, ...] = ()) -> Any:
    if key_path and _is_sensitive_key(key_path[-1]):
        return _REDACTION_TOKEN

    if value is None or isinstance(value, (str, int, float, bool)):
        if isinstance(value, str):
            return _truncate_str(value)
        return value

    if isinstance(value, dict):
        items = list(value.items())
        sanitized = {
            str(k): _sanitize(v, (*key_path, str(k)))
            for k, v in items[:_MAX_COLLECTION_ITEMS]
        }
        if len(items) > _MAX_COLLECTION_ITEMS:
            sanitized["_truncated_items"] = len(items) - _MAX_COLLECTION_ITEMS
        return sanitized

    if isinstance(value, (list, tuple, set)):
        seq = list(value)
        sanitized = [_sanitize(v, key_path) for v in seq[:_MAX_COLLECTION_ITEMS]]
        if len(seq) > _MAX_COLLECTION_ITEMS:
            sanitized.append(f"...[truncated:{len(seq) - _MAX_COLLECTION_ITEMS}]")
        return sanitized

    return _truncate_str(repr(value))


def elapsed_ms(start_time: float) -> float:
    return round((time.perf_counter() - start_time) * 1000, 3)


def set_current_trace_id(trace_id: str | None) -> Token:
    return _TRACE_ID_CTX.set(trace_id)


def reset_current_trace_id(token: Token) -> None:
    _TRACE_ID_CTX.reset(token)


def get_current_trace_id() -> str | None:
    return _TRACE_ID_CTX.get()


# O3 — Correlation ID context var for span-level log correlation
_CORRELATION_ID_CTX: ContextVar[str | None] = ContextVar(
    "agent_skills_correlation_id", default=None
)


def set_correlation_id(correlation_id: str | None) -> Token:
    return _CORRELATION_ID_CTX.set(correlation_id)


def get_correlation_id() -> str | None:
    return _CORRELATION_ID_CTX.get()


def log_event(event: str, level: str = "info", **fields: Any) -> None:
    trace_id = fields.get("trace_id") or get_current_trace_id()
    correlation_id = fields.get("correlation_id") or get_correlation_id()
    payload = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "event": event,
        "trace_id": trace_id,
        "correlation_id": correlation_id,
    }
    payload.update({k: _sanitize(v) for k, v in fields.items()})

    message = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
    logger_fn = getattr(_LOGGER, level, _LOGGER.info)
    logger_fn(message)

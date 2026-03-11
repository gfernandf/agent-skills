from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

_LOGGER_NAME = "agent_skills"
_LOG_LEVEL = os.getenv("AGENT_SKILLS_LOG_LEVEL", "INFO").upper()


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


def _sanitize(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _sanitize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_sanitize(v) for v in value]
    return repr(value)


def elapsed_ms(start_time: float) -> float:
    return round((time.perf_counter() - start_time) * 1000, 3)


def log_event(event: str, level: str = "info", **fields: Any) -> None:
    payload = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "event": event,
    }
    payload.update({k: _sanitize(v) for k, v in fields.items()})

    message = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
    logger_fn = getattr(_LOGGER, level, _LOGGER.info)
    logger_fn(message)

"""
Webhook delivery system for agent-skills.

Provides event subscription management and reliable delivery with
retry and HMAC signature verification.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.request import Request, urlopen
from urllib.error import URLError

logger = logging.getLogger(__name__)

# ── Event types ──────────────────────────────────────────────────
VALID_EVENT_TYPES = frozenset({
    "skill.started",
    "skill.completed",
    "skill.failed",
    "run.completed",
    "run.failed",
})

# ── Configuration ────────────────────────────────────────────────
_MAX_RETRIES = 3
_RETRY_BACKOFF_BASE = 2.0   # seconds: 2, 4, 8
_DELIVERY_TIMEOUT = 10       # seconds per attempt
_MAX_SUBSCRIPTIONS = 100


@dataclass
class WebhookSubscription:
    id: str
    url: str
    events: list[str]
    secret: str = ""          # HMAC-SHA256 shared secret
    active: bool = True
    created_at: str = ""


@dataclass
class WebhookStore:
    """Thread-safe in-memory webhook subscription store."""

    _subscriptions: dict[str, WebhookSubscription] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    max_subscriptions: int = _MAX_SUBSCRIPTIONS

    def register(self, sub: WebhookSubscription) -> None:
        for evt in sub.events:
            if evt != "*" and evt not in VALID_EVENT_TYPES:
                raise ValueError(f"Unknown event type: {evt}")
        with self._lock:
            if len(self._subscriptions) >= self.max_subscriptions:
                raise RuntimeError("Max webhook subscriptions reached")
            self._subscriptions[sub.id] = sub

    def unregister(self, sub_id: str) -> bool:
        with self._lock:
            return self._subscriptions.pop(sub_id, None) is not None

    def list_subscriptions(self) -> list[dict]:
        with self._lock:
            return [
                {"id": s.id, "url": s.url, "events": s.events, "active": s.active}
                for s in self._subscriptions.values()
            ]

    def get_subscribers(self, event_type: str) -> list[WebhookSubscription]:
        with self._lock:
            return [
                s for s in self._subscriptions.values()
                if s.active and (event_type in s.events or "*" in s.events)
            ]


def _sign_payload(payload: bytes, secret: str) -> str:
    """Compute HMAC-SHA256 signature for webhook verification."""
    return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


def _deliver_one(url: str, payload: bytes, headers: dict[str, str]) -> bool:
    """Attempt a single delivery. Returns True on 2xx."""
    req = Request(url, data=payload, headers=headers, method="POST")
    try:
        with urlopen(req, timeout=_DELIVERY_TIMEOUT) as resp:
            return 200 <= resp.status < 300
    except (URLError, OSError):
        return False


def deliver_event(
    store: WebhookStore,
    event_type: str,
    data: dict[str, Any],
    *,
    trace_id: str | None = None,
) -> None:
    """Fan-out an event to all matching subscribers with retry.

    Delivery is fire-and-forget on a daemon thread per subscriber
    to avoid blocking the caller.
    """
    subscribers = store.get_subscribers(event_type)
    if not subscribers:
        return

    envelope = {
        "event": event_type,
        "data": data,
        "timestamp": time.time(),
    }
    if trace_id:
        envelope["trace_id"] = trace_id

    payload = json.dumps(envelope, default=str).encode()

    for sub in subscribers:
        t = threading.Thread(
            target=_deliver_with_retry,
            args=(sub, payload),
            daemon=True,
        )
        t.start()


def _deliver_with_retry(sub: WebhookSubscription, payload: bytes) -> None:
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if sub.secret:
        headers["X-Webhook-Signature"] = f"sha256={_sign_payload(payload, sub.secret)}"

    for attempt in range(_MAX_RETRIES + 1):
        if _deliver_one(sub.url, payload, headers):
            logger.debug("webhook delivered to %s (attempt %d)", sub.url, attempt + 1)
            return
        if attempt < _MAX_RETRIES:
            backoff = _RETRY_BACKOFF_BASE ** (attempt + 1)
            time.sleep(backoff)

    logger.warning("webhook delivery failed after %d attempts: %s", _MAX_RETRIES + 1, sub.url)

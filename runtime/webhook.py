"""
Webhook delivery system for agent-skills.

Provides event subscription management and reliable delivery with
retry and HMAC signature verification.
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import logging
import socket
import threading
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse
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

# ── SSRF protection ──────────────────────────────────────────────
_BLOCKED_METADATA_IPS = frozenset({
    "169.254.169.254",  # AWS / GCP / Azure instance metadata
    "100.100.100.200",  # Alibaba Cloud metadata
    "fd00:ec2::254",    # AWS IPv6 metadata
})


def _validate_webhook_url(url: str) -> None:
    """Validate webhook URL to prevent SSRF attacks.

    Blocks:
    - Non-HTTP(S) schemes
    - Cloud metadata endpoints
    - Private/loopback/link-local IPs (unless AGENT_SKILLS_WEBHOOKS_ALLOW_PRIVATE=1)

    Set AGENT_SKILLS_WEBHOOKS_SKIP_URL_VALIDATION=1 for testing only.
    """
    import os

    if os.environ.get("AGENT_SKILLS_WEBHOOKS_SKIP_URL_VALIDATION", "").strip().lower() in ("1", "true"):
        return

    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        raise ValueError(
            f"Webhook URL scheme '{parsed.scheme}' is not allowed. "
            "Only http and https are permitted."
        )

    hostname = parsed.hostname
    if not hostname:
        raise ValueError("Webhook URL has no hostname.")

    try:
        resolved_ips = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as e:
        raise ValueError(f"Cannot resolve webhook hostname '{hostname}'.") from e

    allow_private = os.environ.get("AGENT_SKILLS_WEBHOOKS_ALLOW_PRIVATE", "").strip().lower() in ("1", "true", "yes")

    for _family, _type, _proto, _canonname, sockaddr in resolved_ips:
        ip_str = sockaddr[0]

        if ip_str in _BLOCKED_METADATA_IPS:
            raise ValueError(
                f"Webhook URL resolves to blocked cloud metadata IP {ip_str} "
                f"(hostname '{hostname}'). This is never allowed."
            )

        if not allow_private:
            addr = ipaddress.ip_address(ip_str)
            if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
                raise ValueError(
                    f"Webhook URL resolves to private/reserved IP {ip_str} "
                    f"(hostname '{hostname}'). Set AGENT_SKILLS_WEBHOOKS_ALLOW_PRIVATE=1 "
                    "to permit internal endpoints."
                )


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
        # SSRF protection: validate URL before accepting subscription
        _validate_webhook_url(sub.url)
        # Security: warn if HMAC secret is empty (signatures will be meaningless)
        if not sub.secret:
            import os
            enforce = os.environ.get("AGENT_SKILLS_WEBHOOKS_REQUIRE_SECRET", "").strip().lower()
            if enforce in ("1", "true", "yes"):
                raise ValueError(
                    "Webhook secret is required (AGENT_SKILLS_WEBHOOKS_REQUIRE_SECRET=1). "
                    "Provide a non-empty 'secret' field for HMAC-SHA256 signature verification."
                )
            logger.warning(
                "webhook.insecure_registration id=%s url=%s reason=empty_secret "
                "hint=Set AGENT_SKILLS_WEBHOOKS_REQUIRE_SECRET=1 to enforce secrets",
                sub.id, sub.url,
            )
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
    # I4 — Dead-letter queue: record the failed delivery for later inspection
    _DLQ.append({
        "subscription_id": sub.id,
        "url": sub.url,
        "payload_size": len(payload),
        "attempts": _MAX_RETRIES + 1,
        "failed_at": time.time(),
    })


# ── I4 — In-memory Dead Letter Queue ────────────────────────────────────

class _DeadLetterQueue:
    """Bounded in-memory DLQ for failed webhook deliveries."""

    _MAX_SIZE = 500

    def __init__(self) -> None:
        self._items: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    def append(self, item: dict[str, Any]) -> None:
        with self._lock:
            self._items.append(item)
            if len(self._items) > self._MAX_SIZE:
                self._items = self._items[-self._MAX_SIZE:]

    def list_items(self, *, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            return list(reversed(self._items[-limit:]))

    def clear(self) -> int:
        with self._lock:
            count = len(self._items)
            self._items.clear()
            return count

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._items)


_DLQ = _DeadLetterQueue()


def get_dlq() -> _DeadLetterQueue:
    """Return the global DLQ instance for inspection."""
    return _DLQ

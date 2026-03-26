"""Tests for runtime.webhook module."""

from __future__ import annotations

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import patch

import pytest

os.environ.setdefault("AGENT_SKILLS_WEBHOOKS_SKIP_URL_VALIDATION", "1")
os.environ.setdefault("AGENT_SKILLS_WEBHOOKS_ALLOW_PRIVATE", "1")

from runtime.webhook import (
    WebhookStore,
    WebhookSubscription,
    _sign_payload,
    deliver_event,
)


# ── WebhookStore tests ──────────────────────────────────────────


class TestWebhookStore:
    def test_register_and_list(self):
        store = WebhookStore()
        sub = WebhookSubscription(
            id="s1", url="http://example.com/hook", events=["skill.completed"]
        )
        store.register(sub)
        subs = store.list_subscriptions()
        assert len(subs) == 1
        assert subs[0]["id"] == "s1"

    def test_register_invalid_event_type(self):
        store = WebhookStore()
        sub = WebhookSubscription(
            id="s1", url="http://example.com/hook", events=["bogus.event"]
        )
        with pytest.raises(ValueError, match="Unknown event type"):
            store.register(sub)

    def test_register_wildcard_event(self):
        store = WebhookStore()
        sub = WebhookSubscription(id="s1", url="http://example.com/hook", events=["*"])
        store.register(sub)
        assert len(store.list_subscriptions()) == 1

    def test_unregister(self):
        store = WebhookStore()
        sub = WebhookSubscription(
            id="s1", url="http://example.com/hook", events=["skill.completed"]
        )
        store.register(sub)
        assert store.unregister("s1") is True
        assert store.list_subscriptions() == []

    def test_unregister_missing(self):
        store = WebhookStore()
        assert store.unregister("missing") is False

    def test_get_subscribers_filters_by_event(self):
        store = WebhookStore()
        store.register(
            WebhookSubscription(id="s1", url="http://a.com", events=["skill.completed"])
        )
        store.register(
            WebhookSubscription(id="s2", url="http://b.com", events=["skill.failed"])
        )
        store.register(WebhookSubscription(id="s3", url="http://c.com", events=["*"]))

        completed = store.get_subscribers("skill.completed")
        assert {s.id for s in completed} == {"s1", "s3"}

        failed = store.get_subscribers("skill.failed")
        assert {s.id for s in failed} == {"s2", "s3"}

    def test_inactive_subscriber_excluded(self):
        store = WebhookStore()
        sub = WebhookSubscription(
            id="s1", url="http://a.com", events=["skill.completed"], active=False
        )
        store.register(sub)
        assert store.get_subscribers("skill.completed") == []

    def test_max_subscriptions_enforced(self):
        store = WebhookStore(max_subscriptions=2)
        store.register(
            WebhookSubscription(id="s1", url="http://a.com", events=["skill.completed"])
        )
        store.register(
            WebhookSubscription(id="s2", url="http://b.com", events=["skill.completed"])
        )
        with pytest.raises(RuntimeError, match="Max webhook subscriptions"):
            store.register(
                WebhookSubscription(
                    id="s3", url="http://c.com", events=["skill.completed"]
                )
            )


# ── Signature tests ─────────────────────────────────────────────


class TestSignature:
    def test_sign_payload_deterministic(self):
        payload = b'{"event":"skill.completed"}'
        sig1 = _sign_payload(payload, "secret123")
        sig2 = _sign_payload(payload, "secret123")
        assert sig1 == sig2
        assert len(sig1) == 64  # SHA-256 hex

    def test_sign_payload_different_secrets(self):
        payload = b'{"event":"skill.completed"}'
        sig1 = _sign_payload(payload, "secret1")
        sig2 = _sign_payload(payload, "secret2")
        assert sig1 != sig2


# ── Delivery tests ──────────────────────────────────────────────


class TestDelivery:
    def test_deliver_event_no_subscribers(self):
        """Should not raise when there are no subscribers."""
        store = WebhookStore()
        deliver_event(store, "skill.completed", {"skill_id": "test"})

    def test_deliver_event_calls_endpoint(self):
        """Verify event is actually delivered to a local HTTP server."""
        received = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length)
                received.append(json.loads(body))
                self.send_response(200)
                self.end_headers()

            def log_message(self, *args):
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        port = server.server_address[1]
        t = threading.Thread(target=server.handle_request, daemon=True)
        t.start()

        store = WebhookStore()
        store.register(
            WebhookSubscription(
                id="s1",
                url=f"http://127.0.0.1:{port}/hook",
                events=["skill.completed"],
            )
        )

        deliver_event(store, "skill.completed", {"skill_id": "demo"}, trace_id="t-123")

        t.join(timeout=5)
        server.server_close()

        assert len(received) == 1
        assert received[0]["event"] == "skill.completed"
        assert received[0]["data"]["skill_id"] == "demo"
        assert received[0]["trace_id"] == "t-123"

    def test_deliver_event_includes_signature(self):
        """HMAC signature header present when secret is set."""
        received_headers = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                received_headers.append(dict(self.headers))
                self.send_response(200)
                self.end_headers()

            def log_message(self, *args):
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        port = server.server_address[1]
        t = threading.Thread(target=server.handle_request, daemon=True)
        t.start()

        store = WebhookStore()
        store.register(
            WebhookSubscription(
                id="s1",
                url=f"http://127.0.0.1:{port}/hook",
                events=["skill.completed"],
                secret="my-secret",
            )
        )

        deliver_event(store, "skill.completed", {"skill_id": "demo"})

        t.join(timeout=5)
        server.server_close()

        assert len(received_headers) == 1
        sig_header = received_headers[0].get("X-Webhook-Signature", "")
        assert sig_header.startswith("sha256=")

    def test_deliver_event_retries_on_failure(self):
        """Should retry on server error and succeed on the second attempt."""
        attempt_count = {"n": 0}

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                attempt_count["n"] += 1
                if attempt_count["n"] == 1:
                    self.send_response(500)
                    self.end_headers()
                else:
                    self.send_response(200)
                    self.end_headers()

            def log_message(self, *args):
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        port = server.server_address[1]
        t = threading.Thread(
            target=lambda: [server.handle_request() for _ in range(2)], daemon=True
        )
        t.start()

        store = WebhookStore()
        store.register(
            WebhookSubscription(
                id="s1",
                url=f"http://127.0.0.1:{port}/hook",
                events=["skill.completed"],
            )
        )

        # Reduce backoff for test speed
        with patch("runtime.webhook._RETRY_BACKOFF_BASE", 0.1):
            deliver_event(store, "skill.completed", {"skill_id": "demo"})

        t.join(timeout=10)
        server.server_close()

        assert attempt_count["n"] == 2

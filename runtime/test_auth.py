"""Tests for runtime.auth RBAC module."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

import pytest

from runtime.auth import (
    ANONYMOUS,
    ApiKeyStore,
    AuthMiddleware,
    Identity,
    JWTVerifier,
    ROLES,
    has_role,
    required_role_for,
)


class TestRoleHierarchy:
    def test_role_order(self):
        assert ROLES == ("reader", "executor", "operator", "admin")

    def test_has_role_exact(self):
        assert has_role("reader", "reader")
        assert has_role("admin", "admin")

    def test_has_role_higher(self):
        assert has_role("admin", "reader")
        assert has_role("operator", "executor")
        assert has_role("executor", "reader")

    def test_has_role_lower_denied(self):
        assert not has_role("reader", "executor")
        assert not has_role("executor", "operator")
        assert not has_role("operator", "admin")

    def test_has_role_unknown(self):
        assert not has_role("unknown", "reader")


class TestRouteRoles:
    def test_health_is_reader(self):
        assert required_role_for("GET", "/v1/health") == "reader"

    def test_list_is_reader(self):
        assert required_role_for("GET", "/v1/skills/list") == "reader"

    def test_execute_is_executor(self):
        assert required_role_for("POST", "/v1/skills/my-skill/execute") == "executor"

    def test_stream_is_executor(self):
        assert required_role_for("POST", "/v1/skills/my-skill/execute/stream") == "executor"

    def test_discover_is_reader(self):
        assert required_role_for("POST", "/v1/skills/discover") == "reader"

    def test_webhooks_post_is_operator(self):
        assert required_role_for("POST", "/v1/webhooks") == "operator"

    def test_webhooks_delete_is_operator(self):
        assert required_role_for("DELETE", "/v1/webhooks/some-id") == "operator"

    def test_runs_is_operator(self):
        assert required_role_for("GET", "/v1/runs") == "operator"

    def test_unknown_route_requires_admin(self):
        assert required_role_for("POST", "/v1/unknown") == "admin"


class TestIdentity:
    def test_identity_has_role(self):
        admin = Identity(subject="u1", role="admin")
        assert admin.has_role("reader")
        assert admin.has_role("admin")

    def test_anonymous_is_reader(self):
        assert ANONYMOUS.role == "reader"
        assert ANONYMOUS.has_role("reader")
        assert not ANONYMOUS.has_role("executor")


class TestApiKeyStore:
    def test_register_and_authenticate(self):
        store = ApiKeyStore()
        store.register("key-abc-123", subject="alice", role="executor")
        identity = store.authenticate("key-abc-123")
        assert identity is not None
        assert identity.subject == "alice"
        assert identity.role == "executor"

    def test_invalid_key_returns_none(self):
        store = ApiKeyStore()
        store.register("valid-key", subject="bob", role="admin")
        assert store.authenticate("wrong-key") is None

    def test_empty_store(self):
        store = ApiKeyStore()
        assert store.authenticate("anything") is None


class TestAuthMiddleware:
    def test_api_key_auth(self):
        mw = AuthMiddleware()
        mw.api_key_store.register("test-key", subject="user1", role="admin")
        identity = mw.authenticate({"x-api-key": "test-key"})
        assert identity is not None
        assert identity.subject == "user1"

    def test_invalid_api_key_rejects(self):
        mw = AuthMiddleware()
        mw.api_key_store.register("test-key", subject="user1", role="admin")
        identity = mw.authenticate({"x-api-key": "wrong"})
        assert identity is None

    def test_bearer_token(self):
        def verifier(token):
            if token == "valid-token":
                return Identity(subject="jwt-user", role="executor")
            return None

        mw = AuthMiddleware(token_verifier=verifier)
        identity = mw.authenticate({"authorization": "Bearer valid-token"})
        assert identity is not None
        assert identity.subject == "jwt-user"

    def test_bearer_token_invalid(self):
        mw = AuthMiddleware()
        identity = mw.authenticate({"authorization": "Bearer invalid"})
        assert identity is None

    def test_anonymous_allowed(self):
        mw = AuthMiddleware(allow_anonymous=True, anonymous_role="reader")
        identity = mw.authenticate({})
        assert identity is not None
        assert identity.role == "reader"

    def test_anonymous_denied_by_default(self):
        mw = AuthMiddleware()
        identity = mw.authenticate({})
        assert identity is None

    def test_authorize_reader_on_health(self):
        mw = AuthMiddleware()
        reader = Identity(subject="u1", role="reader")
        assert mw.authorize(reader, "GET", "/v1/health")

    def test_authorize_reader_denied_execute(self):
        mw = AuthMiddleware()
        reader = Identity(subject="u1", role="reader")
        assert not mw.authorize(reader, "POST", "/v1/skills/s1/execute")

    def test_authorize_executor_on_execute(self):
        mw = AuthMiddleware()
        executor = Identity(subject="u1", role="executor")
        assert mw.authorize(executor, "POST", "/v1/skills/s1/execute")

    def test_authorize_none_identity(self):
        mw = AuthMiddleware()
        assert not mw.authorize(None, "GET", "/v1/health")


def _make_jwt(payload: dict, secret: str) -> str:
    """Build a minimal HS256 JWT for testing."""
    header = base64.urlsafe_b64encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode()).rstrip(b"=").decode()
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    signing_input = f"{header}.{body}".encode()
    sig = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
    sig_b64 = base64.urlsafe_b64encode(sig).rstrip(b"=").decode()
    return f"{header}.{body}.{sig_b64}"


class TestJWTVerifier:
    SECRET = "test-secret-256"

    def test_valid_token(self):
        verifier = JWTVerifier(self.SECRET)
        token = _make_jwt({"sub": "alice", "role": "admin"}, self.SECRET)
        identity = verifier(token)
        assert identity is not None
        assert identity.subject == "alice"
        assert identity.role == "admin"

    def test_default_role(self):
        verifier = JWTVerifier(self.SECRET, default_role="reader")
        token = _make_jwt({"sub": "bob"}, self.SECRET)
        identity = verifier(token)
        assert identity is not None
        assert identity.role == "reader"

    def test_expired_token_rejected(self):
        verifier = JWTVerifier(self.SECRET)
        token = _make_jwt({"sub": "alice", "exp": int(time.time()) - 100}, self.SECRET)
        assert verifier(token) is None

    def test_future_expiry_accepted(self):
        verifier = JWTVerifier(self.SECRET)
        token = _make_jwt({"sub": "alice", "exp": int(time.time()) + 3600}, self.SECRET)
        assert verifier(token) is not None

    def test_wrong_secret_rejected(self):
        verifier = JWTVerifier(self.SECRET)
        token = _make_jwt({"sub": "alice"}, "wrong-secret")
        assert verifier(token) is None

    def test_malformed_token_rejected(self):
        verifier = JWTVerifier(self.SECRET)
        assert verifier("not.a.real.token") is None
        assert verifier("garbage") is None
        assert verifier("") is None

    def test_invalid_role_falls_back(self):
        verifier = JWTVerifier(self.SECRET, default_role="executor")
        token = _make_jwt({"sub": "alice", "role": "superuser"}, self.SECRET)
        identity = verifier(token)
        assert identity is not None
        assert identity.role == "executor"

    def test_middleware_with_jwt_bearer(self):
        verifier = JWTVerifier(self.SECRET)
        mw = AuthMiddleware(token_verifier=verifier)
        token = _make_jwt({"sub": "alice", "role": "operator"}, self.SECRET)
        identity = mw.authenticate({"authorization": f"Bearer {token}"})
        assert identity is not None
        assert identity.subject == "alice"
        assert identity.role == "operator"

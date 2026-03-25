"""
Pluggable authentication and RBAC middleware for agent-skills.

Roles (ordered by privilege):
    reader   → read-only endpoints (health, describe, list, governance)
    executor → reader + execute (sync, stream, async)
    operator → executor + webhooks, runs management
    admin    → operator + all destructive / config operations

Authentication is handled by pluggable backends. The built-in backends are:
    - api_key  : X-API-Key header (existing behaviour, now with per-key roles)
    - bearer   : Authorization: Bearer <token> with pluggable token verifier

Token verifiers can be registered for JWT (HS256/RS256) or custom schemes.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)

# ── Role hierarchy ───────────────────────────────────────────────

ROLES = ("reader", "executor", "operator", "admin")
_ROLE_RANK: dict[str, int] = {r: i for i, r in enumerate(ROLES)}


def has_role(actual: str, required: str) -> bool:
    """Return True if *actual* role is >= *required* in the hierarchy."""
    return _ROLE_RANK.get(actual, -1) >= _ROLE_RANK.get(required, 999)


# ── Route → required role mapping ────────────────────────────────

# prefix-based: longest match wins
_ROUTE_ROLES: list[tuple[str, str, str]] = [
    # (method, path_prefix, min_role)
    ("GET",    "/v1/health",               "reader"),
    ("GET",    "/openapi.json",            "reader"),
    ("GET",    "/v1/skills/list",          "reader"),
    ("GET",    "/v1/skills/diagnostics",   "reader"),
    ("GET",    "/v1/skills/governance",    "reader"),
    ("GET",    "/v1/skills/",              "reader"),     # describe
    ("POST",   "/v1/skills/discover",      "reader"),
    ("POST",   "/v1/skills/",              "executor"),   # execute, stream, async, attach
    ("POST",   "/v1/capabilities/",        "executor"),
    ("GET",    "/v1/runs",                 "operator"),
    ("POST",   "/v1/webhooks",             "operator"),
    ("GET",    "/v1/webhooks",             "operator"),
    ("DELETE", "/v1/webhooks/",            "operator"),
]


def required_role_for(method: str, path: str) -> str:
    """Resolve the minimum role needed for a given HTTP method + path."""
    method_u = method.upper()
    best: str = "admin"  # unknown routes require admin
    best_len = 0
    for m, prefix, role in _ROUTE_ROLES:
        if m == method_u and path.startswith(prefix) and len(prefix) > best_len:
            best = role
            best_len = len(prefix)
    return best


# ── Identity context ─────────────────────────────────────────────

@dataclass(frozen=True)
class Identity:
    """Authenticated caller identity."""
    subject: str          # user id or key id
    role: str = "reader"
    metadata: dict[str, Any] = field(default_factory=dict)

    def has_role(self, required: str) -> bool:
        return has_role(self.role, required)


ANONYMOUS = Identity(subject="anonymous", role="reader")


# ── API-key store ────────────────────────────────────────────────

@dataclass
class ApiKeyEntry:
    key_hash: str       # SHA-256 hex of the actual key
    subject: str
    role: str = "admin"


class ApiKeyStore:
    """In-memory API key registry with constant-time comparison."""

    def __init__(self) -> None:
        self._entries: dict[str, ApiKeyEntry] = {}  # key_hash → entry

    def register(self, raw_key: str, subject: str, role: str = "admin") -> None:
        h = hashlib.sha256(raw_key.encode()).hexdigest()
        self._entries[h] = ApiKeyEntry(key_hash=h, subject=subject, role=role)

    def authenticate(self, raw_key: str) -> Identity | None:
        h = hashlib.sha256(raw_key.encode()).hexdigest()
        entry = self._entries.get(h)
        if entry is None:
            return None
        return Identity(subject=entry.subject, role=entry.role)


# ── Bearer token verifier interface ──────────────────────────────

TokenVerifier = Callable[[str], Identity | None]


def _noop_verifier(token: str) -> Identity | None:
    """Placeholder verifier that always rejects."""
    return None


class JWTVerifier:
    """HMAC-SHA256 JWT token verifier (HS256).

    Decodes JWTs with the configured shared secret. Extracts ``sub`` and
    ``role`` claims to build an Identity.  Falls back to *default_role*
    when the token has no ``role`` claim.

    Does NOT depend on any external library — uses stdlib only.
    """

    def __init__(self, secret: str, *, default_role: str = "executor") -> None:
        self._secret = secret.encode()
        self._default_role = default_role

    def __call__(self, token: str) -> Identity | None:
        import base64
        parts = token.split(".")
        if len(parts) != 3:
            return None
        try:
            header_b64, payload_b64, sig_b64 = parts
            # Verify signature (HS256)
            signing_input = f"{header_b64}.{payload_b64}".encode()
            expected_sig = hmac.new(self._secret, signing_input, hashlib.sha256).digest()
            # URL-safe base64 decode the signature
            sig_padded = sig_b64 + "=" * (-len(sig_b64) % 4)
            actual_sig = base64.urlsafe_b64decode(sig_padded)
            if not hmac.compare_digest(expected_sig, actual_sig):
                return None
            # Decode payload
            payload_padded = payload_b64 + "=" * (-len(payload_b64) % 4)
            payload = json.loads(base64.urlsafe_b64decode(payload_padded))
            # Check expiry
            exp = payload.get("exp")
            if isinstance(exp, (int, float)) and exp < time.time():
                return None
            sub = payload.get("sub", "unknown")
            role = payload.get("role", self._default_role)
            if role not in _ROLE_RANK:
                role = self._default_role
            return Identity(subject=str(sub), role=role, metadata={"jwt_claims": payload})
        except Exception:
            return None


# ── Auth middleware ──────────────────────────────────────────────

@dataclass
class AuthMiddleware:
    """
    Pluggable authentication for the HTTP server.

    Usage in _RequestHandler:
        identity = middleware.authenticate(headers)
        if not middleware.authorize(identity, method, path):
            → 403
    """
    api_key_store: ApiKeyStore = field(default_factory=ApiKeyStore)
    token_verifier: TokenVerifier = _noop_verifier
    allow_anonymous: bool = False
    anonymous_role: str = "reader"

    def authenticate(self, headers: dict[str, str]) -> Identity | None:
        """Try all auth schemes. Returns Identity or None (unauthenticated)."""
        # 1. X-API-Key
        api_key = headers.get("x-api-key") or headers.get("X-API-Key")
        if api_key:
            identity = self.api_key_store.authenticate(api_key)
            if identity:
                return identity
            return None  # key provided but invalid → reject

        # 2. Authorization: Bearer <token>
        auth_header = headers.get("authorization") or headers.get("Authorization")
        if auth_header and auth_header.lower().startswith("bearer "):
            token = auth_header[7:].strip()
            if token:
                return self.token_verifier(token)

        # 3. Anonymous fallback
        if self.allow_anonymous:
            return Identity(subject="anonymous", role=self.anonymous_role)

        return None

    def authorize(self, identity: Identity | None, method: str, path: str) -> bool:
        """Check if identity has the required role for the route."""
        if identity is None:
            return False
        required = required_role_for(method, path)
        return identity.has_role(required)

from __future__ import annotations

import ipaddress
import json
import logging
import os
import re
import socket
import time
from typing import Any
from urllib.parse import urlparse

import requests

from runtime.binding_models import InvocationRequest, InvocationResponse
from runtime.errors import RuntimeErrorBase


class OpenAPIInvocationError(RuntimeErrorBase):
    """Raised when an OpenAPI invocation fails."""


# HTTP status codes that are considered transient and eligible for retry.
_TRANSIENT_STATUS_CODES = frozenset({429, 502, 503, 504})

_DEFAULT_MAX_RETRIES = 3
_DEFAULT_RETRY_BACKOFF_BASE = 1.0
_DEFAULT_RETRY_BACKOFF_FACTOR = 2.0
_MAX_RETRY_AFTER_SECONDS = 60.0

_DEFAULT_MAX_REQUEST_BYTES = int(os.getenv("AGENT_SKILLS_MAX_REQUEST_BYTES", str(10 * 1024 * 1024)))
_DEFAULT_MAX_RESPONSE_BYTES = int(os.getenv("AGENT_SKILLS_MAX_RESPONSE_BYTES", str(10 * 1024 * 1024)))


class OpenAPIInvoker:
    """
    Execute a binding invocation against an OpenAPI-compatible HTTP service.

    Assumptions for v1:
    - binding.operation_id represents the HTTP path
    - HTTP method defaults to POST unless metadata specifies otherwise
    - payload is sent as JSON
    - response body is expected to be JSON
    """

    DEFAULT_TIMEOUT_SECONDS = 30.0
    ALLOWED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
    _ENV_PLACEHOLDER = re.compile(r"\$\{([A-Z][A-Z0-9_]*)\}")

    # Cloud metadata endpoints that are ALWAYS blocked regardless of allow_private_networks.
    _BLOCKED_METADATA_IPS = frozenset({
        "169.254.169.254",  # AWS / GCP / Azure instance metadata
        "100.100.100.200",  # Alibaba Cloud metadata
        "fd00:ec2::254",    # AWS IPv6 metadata
    })

    _SESSION_POOL_MAX = 32

    def __init__(self, *, allow_private_networks: bool = True) -> None:
        """
        Args:
            allow_private_networks: When True (default) private/loopback IPs are
                allowed so local services (e.g. localhost OpenAI proxy) work.
                Set to False in hardened deployments to block RFC-1918, loopback,
                and link-local addresses.
        """
        self._allow_private_networks = allow_private_networks
        self._logger = logging.getLogger(__name__)
        # Connection-pooled sessions keyed by base_url for persistent TCP reuse
        self._sessions: dict[str, requests.Session] = {}
        self._sessions_lock = __import__("threading").Lock()

    def _get_session(self, base_url: str) -> requests.Session:
        """Return a pooled Session for the given base_url, creating one if needed."""
        session = self._sessions.get(base_url)
        if session is not None:
            return session
        with self._sessions_lock:
            # Double-check after acquiring lock
            session = self._sessions.get(base_url)
            if session is not None:
                return session
            # Evict oldest if pool is full
            if len(self._sessions) >= self._SESSION_POOL_MAX:
                oldest_key = next(iter(self._sessions))
                self._sessions.pop(oldest_key).close()
            session = requests.Session()
            adapter = requests.adapters.HTTPAdapter(pool_connections=4, pool_maxsize=10)
            session.mount("https://", adapter)
            session.mount("http://", adapter)
            self._sessions[base_url] = session
            return session

    def close_sessions(self) -> None:
        """Close all pooled HTTP sessions. Call on server shutdown."""
        with self._sessions_lock:
            for session in self._sessions.values():
                session.close()
            self._sessions.clear()

    def invoke(self, request: InvocationRequest) -> InvocationResponse:
        start_time = time.perf_counter()
        service = request.service
        binding = request.binding
        capability_id = request.context_metadata.get("capability_id")

        if service.base_url is None:
            raise OpenAPIInvocationError(
                f"Service '{service.id}' does not define a base_url.",
                capability_id=capability_id,
            )

        url = self._build_url(service.base_url, binding.operation_id)

        method = self._resolve_method(binding.metadata.get("method", "POST"), capability_id)
        timeout_seconds = self._resolve_timeout_seconds(
            binding_timeout=binding.metadata.get("timeout_seconds"),
            service_timeout=service.metadata.get("timeout_seconds"),
            capability_id=capability_id,
        )
        headers = self._merge_headers(
            service_headers=service.metadata.get("headers"),
            binding_headers=binding.metadata.get("headers"),
            capability_id=capability_id,
        )

        max_retries = self._resolve_retry_count(
            binding.metadata.get("retry_count"),
            service.metadata.get("retry_count"),
        )
        backoff_base = self._resolve_positive_float(
            binding.metadata.get("retry_backoff_base"),
            service.metadata.get("retry_backoff_base"),
            _DEFAULT_RETRY_BACKOFF_BASE,
        )
        backoff_factor = self._resolve_positive_float(
            binding.metadata.get("retry_backoff_factor"),
            service.metadata.get("retry_backoff_factor"),
            _DEFAULT_RETRY_BACKOFF_FACTOR,
        )

        if os.getenv("AGENT_SKILLS_DEBUG"):
            try:
                safe_headers = self._redact_headers(headers or {})
                safe_payload = self._redact_payload(request.payload)
                with open("artifacts/openai_debug.log", "a", encoding="utf-8") as f:
                    f.write(f"\n[DEBUG] OpenAI request: headers={json.dumps(safe_headers)} "
                            f"payload={json.dumps(safe_payload)[:2000]}\n")
            except Exception:
                pass

        max_request_bytes = self._resolve_positive_int(
            binding.metadata.get("max_request_bytes"),
            service.metadata.get("max_request_bytes"),
            _DEFAULT_MAX_REQUEST_BYTES,
        )
        max_response_bytes = self._resolve_positive_int(
            binding.metadata.get("max_response_bytes"),
            service.metadata.get("max_response_bytes"),
            _DEFAULT_MAX_RESPONSE_BYTES,
        )

        # Validate request payload size
        try:
            payload_bytes = len(json.dumps(request.payload).encode("utf-8")) if request.payload else 0
        except (TypeError, ValueError):
            payload_bytes = 0
        if payload_bytes > max_request_bytes:
            raise OpenAPIInvocationError(
                f"Request payload ({payload_bytes} bytes) exceeds limit "
                f"({max_request_bytes} bytes) for service '{service.id}'.",
                capability_id=capability_id,
            )

        last_error: Exception | None = None
        last_response: requests.Response | None = None
        cancel_event = request.cancel_event

        for attempt in range(max_retries + 1):
            # Cooperative cancellation: abort early if cancelled by engine.
            if cancel_event is not None and cancel_event.is_set():
                raise OpenAPIInvocationError(
                    f"Invocation for service '{service.id}' cancelled.",
                    capability_id=capability_id,
                )

            # W3C trace context propagation (O2)
            trace_id = request.context_metadata.get("trace_id")
            if trace_id:
                from runtime.trace_context import inject_traceparent, trace_id_from_internal
                tp_headers = inject_traceparent(trace_id_from_internal(trace_id))
                headers = dict(headers or {})
                headers.update(tp_headers)

            try:
                session = self._get_session(service.base_url)
                response = session.request(
                    method=method,
                    url=url,
                    json=request.payload,
                    headers=headers or None,
                    timeout=timeout_seconds,
                )
            except requests.Timeout as e:
                last_error = e
                if attempt < max_retries:
                    self._wait_backoff(attempt, backoff_base, backoff_factor)
                    continue
                raise OpenAPIInvocationError(
                    f"HTTP request timed out for service '{service.id}' "
                    f"after {max_retries + 1} attempt(s).",
                    capability_id=capability_id,
                    cause=e,
                ) from e
            except requests.ConnectionError as e:
                last_error = e
                if attempt < max_retries:
                    self._wait_backoff(attempt, backoff_base, backoff_factor)
                    continue
                raise OpenAPIInvocationError(
                    f"HTTP connection failed for service '{service.id}' "
                    f"after {max_retries + 1} attempt(s).",
                    capability_id=capability_id,
                    cause=e,
                ) from e
            except requests.RequestException as e:
                raise OpenAPIInvocationError(
                    f"HTTP request failed for service '{service.id}'.",
                    capability_id=capability_id,
                    cause=e,
                ) from e

            if response.status_code in _TRANSIENT_STATUS_CODES and attempt < max_retries:
                last_response = response
                wait = self._extract_retry_after(response, attempt, backoff_base, backoff_factor)
                time.sleep(wait)
                continue

            # Non-transient or last attempt — break out of retry loop.
            break

        if os.getenv("AGENT_SKILLS_DEBUG"):
            try:
                safe_body = self._redact_response_text(response.text[:2000])
                with open("artifacts/openai_debug.log", "a", encoding="utf-8") as f:
                    f.write(f"[DEBUG] OpenAI response: status={response.status_code} "
                            f"body={safe_body}\n")
            except Exception:
                pass

        # Validate response size
        content_length = len(response.content)
        if content_length > max_response_bytes:
            raise OpenAPIInvocationError(
                f"Response body ({content_length} bytes) exceeds limit "
                f"({max_response_bytes} bytes) from service '{service.id}'.",
                capability_id=capability_id,
            )

        if not response.ok:
            preview = self._safe_text_preview(response.text)
            raise OpenAPIInvocationError(
                (
                    f"Service '{service.id}' returned HTTP {response.status_code}."
                    + (f" Body preview: {preview}" if preview else "")
                ),
                capability_id=capability_id,
            )

        response_mode = self._resolve_response_mode(
            binding.metadata.get("response_mode", "json"),
            capability_id=capability_id,
        )

        if response_mode == "json":
            if response.status_code == 204:
                body: Any = {}
            else:
                try:
                    body = response.json()
                except json.JSONDecodeError as e:
                    raise OpenAPIInvocationError(
                        f"Service '{service.id}' returned non-JSON response.",
                        capability_id=capability_id,
                        cause=e,
                    ) from e
        elif response_mode == "text":
            body = {"text": response.text}
        else:  # raw
            body = {
                "body": response.text,
                "content_type": response.headers.get("Content-Type"),
            }

        if response_mode == "json":
            body = self._enrich_chat_completion_json(body)

        duration_ms = round((time.perf_counter() - start_time) * 1000, 3)

        return InvocationResponse(
            status="success",
            raw_response=body,
            metadata={
                "http_status": response.status_code,
                "service_id": service.id,
                "method": method,
                "url": url,
                "duration_ms": duration_ms,
                "response_content_type": response.headers.get("Content-Type"),
            },
        )

    def _build_url(self, base_url: str, operation_id: str) -> str:
        base = base_url.rstrip("/")
        path = operation_id.lstrip("/")
        url = f"{base}/{path}"
        self._validate_url(url)
        return url

    def _validate_url(self, url: str) -> None:
        """Guard against SSRF by validating the resolved URL."""
        parsed = urlparse(url)

        if parsed.scheme not in ("http", "https"):
            raise OpenAPIInvocationError(
                f"Blocked request to disallowed scheme '{parsed.scheme}'. "
                "Only http and https are permitted."
            )

        hostname = parsed.hostname
        if not hostname:
            raise OpenAPIInvocationError("Blocked request: URL has no hostname.")

        try:
            resolved_ips = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
        except socket.gaierror as e:
            raise OpenAPIInvocationError(
                f"Cannot resolve hostname '{hostname}'.",
                cause=e,
            ) from e

        for family, _type, _proto, _canonname, sockaddr in resolved_ips:
            ip_str = sockaddr[0]

            # Always block cloud metadata endpoints (even when private networks allowed).
            if ip_str in self._BLOCKED_METADATA_IPS:
                raise OpenAPIInvocationError(
                    f"Blocked request to cloud metadata IP {ip_str} "
                    f"(hostname '{hostname}'). This is never allowed."
                )

            if not self._allow_private_networks:
                addr = ipaddress.ip_address(ip_str)
                if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
                    raise OpenAPIInvocationError(
                        f"Blocked request to private/reserved IP {ip_str} "
                        f"(hostname '{hostname}'). Set allow_private_networks=True "
                        "to permit local-network services."
                    )

    def _resolve_method(self, raw_method: Any, capability_id: str | None) -> str:
        if not isinstance(raw_method, str) or not raw_method:
            raise OpenAPIInvocationError(
                "OpenAPI binding metadata 'method' must be a non-empty string.",
                capability_id=capability_id,
            )
        method = raw_method.upper()
        if method not in self.ALLOWED_METHODS:
            raise OpenAPIInvocationError(
                f"Unsupported HTTP method '{raw_method}'.",
                capability_id=capability_id,
            )
        return method

    def _resolve_timeout_seconds(
        self,
        *,
        binding_timeout: Any,
        service_timeout: Any,
        capability_id: str | None,
    ) -> float:
        chosen = binding_timeout if binding_timeout is not None else service_timeout
        if chosen is None:
            return self.DEFAULT_TIMEOUT_SECONDS

        if not isinstance(chosen, (int, float)) or chosen <= 0:
            raise OpenAPIInvocationError(
                "OpenAPI timeout_seconds must be a positive number.",
                capability_id=capability_id,
            )
        return float(chosen)

    def _merge_headers(
        self,
        *,
        service_headers: Any,
        binding_headers: Any,
        capability_id: str | None,
    ) -> dict[str, str]:
        merged: dict[str, str] = {}
        merged.update(self._normalize_headers(service_headers, "service", capability_id))
        merged.update(self._normalize_headers(binding_headers, "binding", capability_id))
        return merged

    def _normalize_headers(
        self,
        raw_headers: Any,
        source: str,
        capability_id: str | None,
    ) -> dict[str, str]:
        if raw_headers is None:
            return {}

        if not isinstance(raw_headers, dict):
            raise OpenAPIInvocationError(
                f"OpenAPI {source} headers must be a mapping if provided.",
                capability_id=capability_id,
            )

        normalized: dict[str, str] = {}
        for key, value in raw_headers.items():
            if not isinstance(key, str) or not key:
                raise OpenAPIInvocationError(
                    f"OpenAPI {source} headers contain an invalid key.",
                    capability_id=capability_id,
                )
            if not isinstance(value, str):
                raise OpenAPIInvocationError(
                    f"OpenAPI {source} header '{key}' must have a string value.",
                    capability_id=capability_id,
                )
            normalized[key] = self._resolve_env_placeholders(
                value=value,
                header_key=key,
                source=source,
                capability_id=capability_id,
            )

        return normalized

    def _enrich_chat_completion_json(self, body: Any) -> Any:
        """
        Enrich OpenAI-style chat completion JSON responses by parsing any JSON
        object embedded in choices[*].message.content.

        This allows bindings to map structured outputs through paths like:
            response.choices.0.message.content_json.field
        while preserving the original response body unchanged for other bindings.
        """
        if not isinstance(body, dict):
            return body

        choices = body.get("choices")
        if not isinstance(choices, list):
            return body

        for choice in choices:
            if not isinstance(choice, dict):
                continue
            message = choice.get("message")
            if not isinstance(message, dict):
                continue
            content = message.get("content")
            if not isinstance(content, str):
                continue
            parsed = self._try_parse_json(content)
            if parsed is not None:
                message["content_json"] = parsed

        return body

    def _try_parse_json(self, value: str) -> Any | None:
        try:
            return json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return None

    def _resolve_env_placeholders(
        self,
        *,
        value: str,
        header_key: str,
        source: str,
        capability_id: str | None,
    ) -> str:
        """
        Resolve ${ENV_VAR} placeholders in header values.

        Example:
            Authorization: "Bearer ${OPENAI_API_KEY}"
        """

        def _replace(match: re.Match[str]) -> str:
            env_name = match.group(1)
            env_value = os.getenv(env_name)
            if env_value is None:
                raise OpenAPIInvocationError(
                    (
                        f"OpenAPI {source} header '{header_key}' references "
                        f"missing environment variable '{env_name}'."
                    ),
                    capability_id=capability_id,
                )
            return env_value

        return self._ENV_PLACEHOLDER.sub(_replace, value)

    def _resolve_response_mode(self, raw_mode: Any, capability_id: str | None) -> str:
        if not isinstance(raw_mode, str) or not raw_mode:
            raise OpenAPIInvocationError(
                "OpenAPI binding metadata 'response_mode' must be a non-empty string.",
                capability_id=capability_id,
            )

        normalized = raw_mode.lower()
        if normalized not in {"json", "text", "raw"}:
            raise OpenAPIInvocationError(
                f"Unsupported OpenAPI response_mode '{raw_mode}'.",
                capability_id=capability_id,
            )

        return normalized

    def _safe_text_preview(self, text: str | None, *, max_len: int = 180) -> str:
        if not text:
            return ""
        compact = " ".join(text.split())
        return compact[:max_len]

    _SENSITIVE_HEADER_NAMES = frozenset({
        "authorization", "x-api-key", "api-key", "x-secret", "cookie",
    })

    def _redact_headers(self, headers: dict[str, str]) -> dict[str, str]:
        """Return a copy of *headers* with sensitive values replaced by '***'."""
        redacted: dict[str, str] = {}
        for k, v in headers.items():
            if k.lower() in self._SENSITIVE_HEADER_NAMES:
                redacted[k] = "***"
            else:
                redacted[k] = v
        return redacted

    _SENSITIVE_PAYLOAD_KEYS = frozenset({
        "api_key", "apikey", "secret", "password", "token", "access_token",
        "refresh_token", "credentials", "private_key",
    })

    def _redact_payload(self, payload: Any) -> Any:
        """Return a copy of *payload* with sensitive keys redacted."""
        if not isinstance(payload, dict):
            return payload
        redacted: dict[str, Any] = {}
        for k, v in payload.items():
            if k.lower() in self._SENSITIVE_PAYLOAD_KEYS:
                redacted[k] = "***"
            elif isinstance(v, dict):
                redacted[k] = self._redact_payload(v)
            else:
                redacted[k] = v
        return redacted

    def _redact_response_text(self, text: str) -> str:
        """Remove potential secrets from response body text for debug logging."""
        import re
        # Redact JWT-like tokens and long base64 strings that might be keys
        text = re.sub(r'eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}', '***JWT_REDACTED***', text)
        text = re.sub(r'(sk-|pk-|key-)[A-Za-z0-9]{20,}', '***KEY_REDACTED***', text)
        return text

    # ── Retry helpers ──────────────────────────────────────────────

    @staticmethod
    def _resolve_retry_count(binding_val: Any, service_val: Any) -> int:
        chosen = binding_val if binding_val is not None else service_val
        if chosen is None:
            return _DEFAULT_MAX_RETRIES
        if isinstance(chosen, int) and chosen >= 0:
            return chosen
        return _DEFAULT_MAX_RETRIES

    @staticmethod
    def _resolve_positive_float(binding_val: Any, service_val: Any, default: float) -> float:
        chosen = binding_val if binding_val is not None else service_val
        if chosen is None:
            return default
        if isinstance(chosen, (int, float)) and chosen > 0:
            return float(chosen)
        return default

    @staticmethod
    def _resolve_positive_int(binding_val: Any, service_val: Any, default: int) -> int:
        chosen = binding_val if binding_val is not None else service_val
        if chosen is None:
            return default
        if isinstance(chosen, int) and chosen > 0:
            return chosen
        return default

    @staticmethod
    def _wait_backoff(attempt: int, base: float, factor: float) -> None:
        delay = base * (factor ** attempt)
        time.sleep(delay)

    @staticmethod
    def _extract_retry_after(
        response: requests.Response,
        attempt: int,
        backoff_base: float,
        backoff_factor: float,
    ) -> float:
        """Parse Retry-After header if present; fall back to exponential backoff."""
        retry_after = response.headers.get("Retry-After")
        if retry_after is not None:
            try:
                wait = float(retry_after)
                return min(max(wait, 0), _MAX_RETRY_AFTER_SECONDS)
            except (ValueError, TypeError):
                pass
        return backoff_base * (backoff_factor ** attempt)
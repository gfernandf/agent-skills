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

        if os.getenv("AGENT_SKILLS_DEBUG"):
            try:
                safe_headers = self._redact_headers(headers or {})
                with open("artifacts/openai_debug.log", "a", encoding="utf-8") as f:
                    f.write(f"\n[DEBUG] OpenAI request: headers={json.dumps(safe_headers)} "
                            f"payload={json.dumps(request.payload)[:2000]}\n")
            except Exception:
                pass

        try:
            response = requests.request(
                method=method,
                url=url,
                json=request.payload,
                headers=headers or None,
                timeout=timeout_seconds,
            )
        except requests.Timeout as e:
            raise OpenAPIInvocationError(
                f"HTTP request timed out for service '{service.id}'.",
                capability_id=capability_id,
                cause=e,
            ) from e
        except requests.RequestException as e:
            raise OpenAPIInvocationError(
                f"HTTP request failed for service '{service.id}'.",
                capability_id=capability_id,
                cause=e,
            ) from e

        if os.getenv("AGENT_SKILLS_DEBUG"):
            try:
                with open("artifacts/openai_debug.log", "a", encoding="utf-8") as f:
                    f.write(f"[DEBUG] OpenAI response: status={response.status_code} "
                            f"body={response.text[:2000]}\n")
            except Exception:
                pass

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
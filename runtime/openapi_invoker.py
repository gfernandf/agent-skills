from __future__ import annotations

import json
import os
import re
import time
from typing import Any

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
        return f"{base}/{path}"

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
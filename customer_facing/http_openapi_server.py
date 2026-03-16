from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from customer_facing.neutral_api import NeutralRuntimeAPI
from gateway.core import SkillGateway
from runtime.openapi_error_contract import build_http_error_payload, map_runtime_error_to_http


logger = logging.getLogger("customer_facing.http")


@dataclass(frozen=True)
class ServerConfig:
    host: str = "127.0.0.1"
    port: int = 8080
    api_key: str | None = None
    rate_limit_requests: int = 60
    rate_limit_window_seconds: int = 60
    unauthenticated_paths: tuple[str, ...] = ("/openapi.json", "/v1/health")


class _RequestHandler(BaseHTTPRequestHandler):
    api: NeutralRuntimeAPI | None = None
    gateway: SkillGateway | None = None
    openapi_spec_path: Path | None = None
    config: ServerConfig = ServerConfig()
    _rate_lock = threading.Lock()
    _rate_state: dict[str, list[float]] = {}

    def do_GET(self) -> None:  # noqa: N802
        try:
            parsed = urlparse(self.path)
            self._request_start = time.time()
            self._request_path = parsed.path
            if not self._authorize(parsed.path):
                return
            if not self._enforce_rate_limit(parsed.path):
                return
            if parsed.path == "/v1/health":
                self._write_json(200, self._api().health())
                return

            if parsed.path == "/openapi.json":
                self._write_openapi_spec()
                return

            skill_prefix = "/v1/skills/"
            if parsed.path.startswith(skill_prefix) and parsed.path.endswith("/describe"):
                skill_id = parsed.path[len(skill_prefix) : -len("/describe")]
                self._write_json(200, self._api().describe_skill(skill_id))
                return

            if parsed.path == "/v1/skills/governance":
                query = parse_qs(parsed.query or "")
                min_state = query.get("min_state", [None])[0]
                limit_raw = query.get("limit", [20])[0]
                try:
                    limit = int(limit_raw)
                except Exception:
                    limit = 20
                self._write_json(
                    200,
                    self._api().list_skill_governance(min_state=min_state, limit=limit),
                )
                return

            if parsed.path == "/v1/skills/list":
                query = parse_qs(parsed.query or "")
                self._write_json(
                    200,
                    {
                        "skills": [
                            s.to_dict()
                            for s in self._gateway().list_skills(
                                domain=query.get("domain", [None])[0],
                                role=query.get("role", [None])[0],
                                status=query.get("status", [None])[0],
                                invocation=query.get("invocation", [None])[0],
                            )
                        ]
                    },
                )
                return

            if parsed.path == "/v1/skills/diagnostics":
                self._write_json(200, self._gateway().diagnostics())
                return

            self._write_json(404, {"error": {"code": "not_found", "message": "Route not found", "type": "NotFound"}})
        except Exception as e:  # pragma: no cover
            self._write_runtime_error(e)

    def do_POST(self) -> None:  # noqa: N802
        try:
            parsed = urlparse(self.path)
            self._request_start = time.time()
            self._request_path = parsed.path
            if not self._authorize(parsed.path):
                return
            if not self._enforce_rate_limit(parsed.path):
                return
            body = self._read_json_body()

            skill_prefix = "/v1/skills/"
            if parsed.path == "/v1/skills/discover":
                intent = body.get("intent") if isinstance(body, dict) else None
                if not isinstance(intent, str) or not intent:
                    raise ValueError("discover requires non-empty string field 'intent'")

                limit_raw = body.get("limit", 10) if isinstance(body, dict) else 10
                limit = int(limit_raw) if isinstance(limit_raw, int) else 10

                response = {
                    "intent": intent,
                    "results": [
                        r.to_dict()
                        for r in self._gateway().discover(
                            intent=intent,
                            domain=(body.get("domain") if isinstance(body.get("domain"), str) else None),
                            role_filter=(body.get("role") if isinstance(body.get("role"), str) else None),
                            limit=limit,
                        )
                    ],
                }
                self._write_json(200, response)
                return

            if parsed.path.startswith(skill_prefix) and parsed.path.endswith("/attach"):
                skill_id = parsed.path[len(skill_prefix) : -len("/attach")]
                if not isinstance(body, dict):
                    raise ValueError("Request body must be a JSON object")

                target_type = body.get("target_type")
                target_ref = body.get("target_ref")
                inputs = body.get("inputs") if isinstance(body.get("inputs"), dict) else {}

                if not isinstance(target_type, str) or not target_type:
                    raise ValueError("attach requires non-empty string field 'target_type'")
                if not isinstance(target_ref, str) or not target_ref:
                    raise ValueError("attach requires non-empty string field 'target_ref'")

                trace_id = self._extract_trace_id(body)
                include_trace = bool(body.get("include_trace", False))
                required_profile = None
                value = body.get("required_conformance_profile")
                if isinstance(value, str) and value:
                    required_profile = value
                audit_mode = None
                value = body.get("audit_mode")
                if isinstance(value, str) and value:
                    audit_mode = value

                response = self._gateway().attach(
                    skill_id=skill_id,
                    target_type=target_type,
                    target_ref=target_ref,
                    inputs=inputs,
                    trace_id=trace_id,
                    include_trace=include_trace,
                    required_conformance_profile=required_profile,
                    audit_mode=audit_mode,
                )
                self._write_json(200, response.to_dict())
                return

            if parsed.path.startswith(skill_prefix) and parsed.path.endswith("/execute"):
                skill_id = parsed.path[len(skill_prefix) : -len("/execute")]
                inputs = body.get("inputs") if isinstance(body, dict) else {}
                trace_id = self._extract_trace_id(body)
                include_trace = bool(body.get("include_trace", False)) if isinstance(body, dict) else False
                required_profile = None
                if isinstance(body, dict):
                    value = body.get("required_conformance_profile")
                    if isinstance(value, str) and value:
                        required_profile = value
                audit_mode = None
                if isinstance(body, dict):
                    value = body.get("audit_mode")
                    if isinstance(value, str) and value:
                        audit_mode = value
                response = self._api().execute_skill(
                    skill_id=skill_id,
                    inputs=inputs if isinstance(inputs, dict) else {},
                    trace_id=trace_id,
                    include_trace=include_trace,
                    required_conformance_profile=required_profile,
                    audit_mode=audit_mode,
                    execution_channel="http",
                )
                self._write_json(200, response)
                return

            capability_prefix = "/v1/capabilities/"
            if parsed.path.startswith(capability_prefix) and parsed.path.endswith("/execute"):
                capability_id = parsed.path[len(capability_prefix) : -len("/execute")]
                inputs = body.get("inputs") if isinstance(body, dict) else {}
                trace_id = self._extract_trace_id(body)
                required_profile = None
                if isinstance(body, dict):
                    value = body.get("required_conformance_profile")
                    if isinstance(value, str) and value:
                        required_profile = value
                response = self._api().execute_capability(
                    capability_id=capability_id,
                    inputs=inputs if isinstance(inputs, dict) else {},
                    trace_id=trace_id,
                    required_conformance_profile=required_profile,
                )
                self._write_json(200, response)
                return

            if parsed.path.startswith(capability_prefix) and parsed.path.endswith("/explain"):
                capability_id = parsed.path[len(capability_prefix) : -len("/explain")]
                required_profile = None
                if isinstance(body, dict):
                    value = body.get("required_conformance_profile")
                    if isinstance(value, str) and value:
                        required_profile = value
                response = self._api().explain_capability_resolution(
                    capability_id=capability_id,
                    required_conformance_profile=required_profile,
                )
                self._write_json(200, response)
                return

            self._write_json(404, {"error": {"code": "not_found", "message": "Route not found", "type": "NotFound"}})
        except Exception as e:  # pragma: no cover
            self._write_runtime_error(e)

    def _api(self) -> NeutralRuntimeAPI:
        if self.api is None:
            raise RuntimeError("NeutralRuntimeAPI is not configured")
        return self.api

    def _gateway(self) -> SkillGateway:
        if self.gateway is None:
            raise RuntimeError("SkillGateway is not configured")
        return self.gateway

    def _authorize(self, path: str) -> bool:
        config = self.config

        if path in config.unauthenticated_paths:
            return True

        if config.api_key is None:
            return True

        provided = self.headers.get("x-api-key")
        if not provided:
            self._write_json(
                401,
                {
                    "error": {
                        "code": "unauthorized",
                        "message": "Missing API key.",
                        "type": "AuthenticationError",
                    }
                },
            )
            return False

        if provided != config.api_key:
            self._write_json(
                403,
                {
                    "error": {
                        "code": "forbidden",
                        "message": "Invalid API key.",
                        "type": "AuthenticationError",
                    }
                },
            )
            return False

        return True

    def _enforce_rate_limit(self, path: str) -> bool:
        config = self.config

        if path in config.unauthenticated_paths:
            return True

        max_requests = max(1, int(config.rate_limit_requests))
        window_seconds = max(1, int(config.rate_limit_window_seconds))
        now = time.time()

        client_id = self.client_address[0] if self.client_address else "unknown"

        with self._rate_lock:
            events = self._rate_state.get(client_id, [])
            cutoff = now - window_seconds
            events = [ts for ts in events if ts >= cutoff]

            if len(events) >= max_requests:
                self._rate_state[client_id] = events
                self._write_json(
                    429,
                    {
                        "error": {
                            "code": "rate_limited",
                            "message": "Too many requests. Retry later.",
                            "type": "RateLimitError",
                        }
                    },
                )
                return False

            events.append(now)
            self._rate_state[client_id] = events

        return True

    def _extract_trace_id(self, body: Any) -> str | None:
        header_trace = self.headers.get("x-trace-id")
        if header_trace:
            return header_trace
        if isinstance(body, dict):
            trace = body.get("trace_id")
            if isinstance(trace, str) and trace:
                return trace
        return None

    def _read_json_body(self) -> dict[str, Any]:
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length == 0:
            return {}
        raw = self.rfile.read(content_length)
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as e:
            raise ValueError("Request body must be valid JSON") from e

        if not isinstance(parsed, dict):
            raise ValueError("Request body must be a JSON object")
        return parsed

    def _write_openapi_spec(self) -> None:
        spec_path = self.openapi_spec_path
        if spec_path is None or not spec_path.exists():
            self._write_json(404, {"error": {"code": "not_found", "message": "OpenAPI spec not found", "type": "NotFound"}})
            return
        raw = spec_path.read_text(encoding="utf-8")
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            self.send_response(200)
            self.send_header("Content-Type", "application/yaml")
            self.end_headers()
            self.wfile.write(raw.encode("utf-8"))
            return
        self._write_json(200, body)

    def _write_runtime_error(self, error: Exception) -> None:
        trace_id = self.headers.get("x-trace-id")
        logger.exception(
            "customer_http_error method=%s path=%s trace_id=%s error_type=%s",
            self.command,
            getattr(self, "_request_path", self.path),
            trace_id or "-",
            type(error).__name__,
        )
        contract = map_runtime_error_to_http(error)
        payload = build_http_error_payload(error, trace_id=trace_id)
        self._write_json(contract.status_code, payload)

    def _write_json(self, status: int, body: dict[str, Any]) -> None:
        encoded = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

        elapsed_ms = -1
        request_start = getattr(self, "_request_start", None)
        if isinstance(request_start, float):
            elapsed_ms = int((time.time() - request_start) * 1000)

        error_code = "-"
        error_obj = body.get("error") if isinstance(body, dict) else None
        if isinstance(error_obj, dict) and isinstance(error_obj.get("code"), str):
            error_code = error_obj["code"]

        client_id = self.client_address[0] if self.client_address else "unknown"
        logger.info(
            "customer_http_request method=%s path=%s status=%s client=%s duration_ms=%s error_code=%s",
            self.command,
            getattr(self, "_request_path", self.path),
            status,
            client_id,
            elapsed_ms,
            error_code,
        )

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return


def run_server(
    api: NeutralRuntimeAPI,
    gateway: SkillGateway,
    *,
    config: ServerConfig = ServerConfig(),
    openapi_spec_path: Path | None = None,
) -> None:
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
        )

    _RequestHandler.api = api
    _RequestHandler.gateway = gateway
    _RequestHandler.openapi_spec_path = openapi_spec_path
    _RequestHandler.config = config
    _RequestHandler._rate_state = {}

    server = ThreadingHTTPServer((config.host, config.port), _RequestHandler)
    print(f"customer-facing API listening on http://{config.host}:{config.port}")
    logger.info(
        "customer_http_server_started host=%s port=%s auth_enabled=%s rate_limit_requests=%s rate_limit_window_seconds=%s",
        config.host,
        config.port,
        bool(config.api_key),
        config.rate_limit_requests,
        config.rate_limit_window_seconds,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()

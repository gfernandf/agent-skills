from __future__ import annotations

import json
import logging
import threading
import time
import traceback
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from customer_facing.neutral_api import NeutralRuntimeAPI
from gateway.core import SkillGateway
from runtime.observability import elapsed_ms, log_event
from runtime.openapi_error_contract import build_http_error_payload, map_runtime_error_to_http

logger = logging.getLogger(__name__)


def _format_prometheus(snapshot: dict[str, Any]) -> str:
    """Convert a metrics snapshot to Prometheus exposition format."""
    lines: list[str] = []
    lines.append(f"# HELP agent_skills_uptime_seconds Runtime uptime in seconds")
    lines.append(f"# TYPE agent_skills_uptime_seconds gauge")
    lines.append(f"agent_skills_uptime_seconds {snapshot.get('uptime_seconds', 0)}")
    for name, value in snapshot.get("counters", {}).items():
        pname = "agent_skills_" + name.replace(".", "_")
        lines.append(f"# TYPE {pname}_total counter")
        lines.append(f"{pname}_total {value}")
    for name, hist in snapshot.get("histograms", {}).items():
        pname = "agent_skills_" + name.replace(".", "_")
        lines.append(f"# TYPE {pname} summary")
        lines.append(f"{pname}_count {hist.get('count', 0)}")
        lines.append(f"{pname}_sum {hist.get('total', 0)}")
    lines.append("")
    return "\n".join(lines)


@dataclass(frozen=True)
class ServerConfig:
    host: str = "127.0.0.1"
    port: int = 8080
    api_key: str | None = None
    rate_limit_requests: int = 60
    rate_limit_window_seconds: int = 60
    max_request_body_bytes: int = 2 * 1024 * 1024  # 2 MB — ample for JSON skill payloads
    unauthenticated_paths: tuple[str, ...] = ("/openapi.json", "/v1/health")
    cors_allowed_origins: str = ""  # Comma-separated origins, or "*" for any. Empty = no CORS headers.
    trusted_proxies: frozenset[str] = frozenset()  # IPs of trusted reverse proxies for X-Forwarded-For


class _RequestHandler(BaseHTTPRequestHandler):
    api: NeutralRuntimeAPI | None = None
    gateway: SkillGateway | None = None
    openapi_spec_path: Path | None = None
    config: ServerConfig = ServerConfig()
    _rate_lock = threading.Lock()
    _rate_state: dict[str, list[float]] = {}
    _RATE_STATE_MAX_CLIENTS = 10_000
    run_store = None  # RunStore instance (set by run_server)
    _async_pool = None  # ThreadPoolExecutor for async launches
    webhook_store = None  # WebhookStore instance (set by run_server)
    auth_middleware = None  # AuthMiddleware instance (set by run_server)
    _runtime_metrics = None  # RuntimeMetrics instance (set by run_server)

    def do_GET(self) -> None:  # noqa: N802
        try:
            parsed = urlparse(self.path)
            self._request_start = time.perf_counter()
            self._request_path = parsed.path
            if not self._authorize(parsed.path):
                return
            if not self._enforce_rate_limit(parsed.path):
                return
            if parsed.path == "/v1/health":
                query = parse_qs(parsed.query or "")
                if "true" in query.get("deep", []):
                    self._write_json(200, self._deep_health())
                else:
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
                offset_raw = query.get("offset", [0])[0]
                try:
                    offset = max(0, int(offset_raw))
                except (ValueError, TypeError):
                    offset = 0
                limit_raw = query.get("limit", [20])[0]
                try:
                    limit = min(100, max(1, int(limit_raw)))
                except (ValueError, TypeError):
                    limit = 20
                all_skills = self._gateway().list_skills(
                    domain=query.get("domain", [None])[0],
                    role=query.get("role", [None])[0],
                    status=query.get("status", [None])[0],
                    invocation=query.get("invocation", [None])[0],
                )
                total = len(all_skills)
                page = all_skills[offset:offset + limit]
                has_more = (offset + limit) < total
                response_body = {
                    "skills": [s.to_dict() for s in page],
                    "pagination": {
                        "offset": offset,
                        "limit": limit,
                        "total": total,
                        "has_more": has_more,
                    },
                }
                if has_more:
                    response_body["pagination"]["next_offset"] = offset + limit
                self._write_json(200, response_body)
                return

            if parsed.path == "/v1/skills/diagnostics":
                self._write_json(200, self._gateway().diagnostics())
                return

            # ── Metrics endpoint ──────────────────────────────────
            if parsed.path == "/v1/metrics":
                metrics = self._runtime_metrics
                if metrics is None:
                    self._write_json(200, {"uptime_seconds": 0, "counters": {}, "histograms": {}})
                else:
                    self._write_json(200, metrics.snapshot())
                return

            # ── Prometheus metrics (text/plain) ───────────────────
            if parsed.path == "/v1/metrics/prometheus":
                metrics = self._runtime_metrics
                body = _format_prometheus(metrics.snapshot() if metrics else {"uptime_seconds": 0, "counters": {}, "histograms": {}})
                self._write_plain(200, body)
                return

            # ── Webhook endpoints (GET) ────────────────────────────
            if parsed.path == "/v1/webhooks":
                wh_store = self.webhook_store
                if wh_store is None:
                    self._write_json(501, {"error": {"code": "not_implemented", "message": "Webhooks not enabled", "type": "NotImplementedError"}})
                    return
                self._write_json(200, {"subscriptions": wh_store.list_subscriptions()})
                return

            # ── Async run endpoints ──────────────────────────────
            if parsed.path == "/v1/runs":
                store = self.run_store
                if store is None:
                    self._write_json(501, {"error": {"code": "not_implemented", "message": "Async runs not enabled", "type": "NotImplementedError"}})
                    return
                query = parse_qs(parsed.query or "")
                limit_raw = query.get("limit", [100])[0]
                try:
                    limit = int(limit_raw)
                except Exception:
                    limit = 100
                self._write_json(200, self._api().list_runs(run_store=store, limit=limit))
                return

            runs_prefix = "/v1/runs/"
            if parsed.path.startswith(runs_prefix):
                store = self.run_store
                if store is None:
                    self._write_json(501, {"error": {"code": "not_implemented", "message": "Async runs not enabled", "type": "NotImplementedError"}})
                    return
                run_id = parsed.path[len(runs_prefix):]
                response = self._api().get_run(run_id, run_store=store)
                status = 200
                if isinstance(response, dict) and "error" in response:
                    status = 404
                self._write_json(status, response)
                return

            self._write_json(404, {"error": {"code": "not_found", "message": "Route not found", "type": "NotFound"}})
        except Exception as e:  # pragma: no cover
            self._write_runtime_error(e)

    def do_POST(self) -> None:  # noqa: N802
        try:
            parsed = urlparse(self.path)
            self._request_start = time.perf_counter()
            self._request_path = parsed.path
            if not self._authorize(parsed.path):
                return
            if not self._enforce_rate_limit(parsed.path):
                return
            body = self._read_json_body()

            skill_prefix = "/v1/skills/"
            # ── Webhook endpoints (POST) ────────────────────────
            if parsed.path == "/v1/webhooks":
                wh_store = self.webhook_store
                if wh_store is None:
                    self._write_json(501, {"error": {"code": "not_implemented", "message": "Webhooks not enabled", "type": "NotImplementedError"}})
                    return
                if not isinstance(body, dict):
                    raise ValueError("Request body must be a JSON object")
                from uuid import uuid4 as _uuid4
                from runtime.webhook import WebhookSubscription
                import time as _time
                url = body.get("url")
                if not isinstance(url, str) or not url:
                    raise ValueError("webhooks require non-empty string field 'url'")
                events = body.get("events")
                if not isinstance(events, list) or not events:
                    raise ValueError("webhooks require non-empty list field 'events'")
                secret = body.get("secret", "")
                sub_id = str(_uuid4())
                sub = WebhookSubscription(
                    id=sub_id,
                    url=url,
                    events=events,
                    secret=secret if isinstance(secret, str) else "",
                    active=True,
                    created_at=str(_time.time()),
                )
                wh_store.register(sub)
                self._write_json(201, {"id": sub_id, "url": url, "events": events})
                return

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

            if parsed.path.startswith(skill_prefix) and parsed.path.endswith("/execute/stream"):
                skill_id = parsed.path[len(skill_prefix) : -len("/execute/stream")]
                inputs = body.get("inputs") if isinstance(body, dict) else {}
                trace_id = self._extract_trace_id(body)
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

                # Start SSE response
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self._send_cors_headers()
                self._send_security_headers()
                self.end_headers()

                def _sse_emit(event_dict):
                    try:
                        event_type = event_dict.get("type", "event")
                        data = json.dumps(event_dict, ensure_ascii=False, default=str)
                        chunk = f"event: {event_type}\ndata: {data}\n\n"
                        self.wfile.write(chunk.encode("utf-8"))
                        self.wfile.flush()
                    except Exception:
                        pass

                result = self._api().execute_skill_streaming(
                    skill_id=skill_id,
                    inputs=inputs if isinstance(inputs, dict) else {},
                    event_callback=_sse_emit,
                    trace_id=trace_id,
                    required_conformance_profile=required_profile,
                    audit_mode=audit_mode,
                    execution_channel="http-stream",
                )

                # Final result event
                try:
                    final_data = json.dumps(result, ensure_ascii=False, default=str)
                    self.wfile.write(f"event: done\ndata: {final_data}\n\n".encode("utf-8"))
                    self.wfile.flush()
                except Exception:
                    pass
                return

            if parsed.path.startswith(skill_prefix) and parsed.path.endswith("/execute/async"):
                store = self.run_store
                if store is None:
                    self._write_json(501, {"error": {"code": "not_implemented", "message": "Async runs not enabled", "type": "NotImplementedError"}})
                    return
                skill_id = parsed.path[len(skill_prefix) : -len("/execute/async")]
                inputs = body.get("inputs") if isinstance(body, dict) else {}
                trace_id = self._extract_trace_id(body)
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
                response = self._api().execute_skill_async(
                    skill_id=skill_id,
                    inputs=inputs if isinstance(inputs, dict) else {},
                    trace_id=trace_id,
                    required_conformance_profile=required_profile,
                    audit_mode=audit_mode,
                    execution_channel="http-async",
                    run_store=store,
                    async_pool=self._async_pool,
                )
                self._write_json(202, response)
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

        # ── RBAC-aware auth (when AuthMiddleware is configured) ────
        middleware = self.auth_middleware
        if middleware is not None:
            headers_dict = {k.lower(): v for k, v in self.headers.items()}
            identity = middleware.authenticate(headers_dict)
            client_ip = self.client_address[0] if self.client_address else "unknown"
            if identity is None:
                log_event("http.auth.rejected", level="warning", reason="unauthenticated", client=client_ip, path=path)
                self._write_json(401, {"error": {"code": "unauthorized", "message": "Authentication required.", "type": "AuthenticationError"}})
                return False
            method = getattr(self, "command", "GET")
            if not middleware.authorize(identity, method, path):
                log_event("http.auth.forbidden", level="warning", reason="insufficient_role", client=client_ip, path=path, role=identity.role)
                self._write_json(403, {"error": {"code": "forbidden", "message": f"Role '{identity.role}' insufficient for this endpoint.", "type": "AuthorizationError"}})
                return False
            return True

        # ── Legacy flat API-key check (backward-compatible) ────────
        if config.api_key is None:
            return True

        provided = self.headers.get("x-api-key")
        client_ip = self.client_address[0] if self.client_address else "unknown"
        if not provided:
            log_event(
                "http.auth.rejected",
                level="warning",
                reason="missing_api_key",
                client=client_ip,
                path=path,
            )
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
            log_event(
                "http.auth.rejected",
                level="warning",
                reason="invalid_api_key",
                client=client_ip,
                path=path,
            )
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

        client_id = self._resolve_client_id()

        with self._rate_lock:
            # Garbage-collect stale entries to prevent unbounded memory growth.
            stale_clients = [
                cid for cid, timestamps in self._rate_state.items()
                if not timestamps or timestamps[-1] < now - window_seconds
            ]
            for cid in stale_clients:
                del self._rate_state[cid]

            # Hard cap: evict oldest clients if dict exceeds max size.
            if len(self._rate_state) > self._RATE_STATE_MAX_CLIENTS:
                by_recency = sorted(
                    self._rate_state.items(),
                    key=lambda kv: kv[1][-1] if kv[1] else 0,
                )
                excess = len(self._rate_state) - self._RATE_STATE_MAX_CLIENTS
                for cid, _ in by_recency[:excess]:
                    del self._rate_state[cid]

            events = self._rate_state.get(client_id, [])
            cutoff = now - window_seconds
            events = [ts for ts in events if ts >= cutoff]

            if len(events) >= max_requests:
                self._rate_state[client_id] = events
                log_event(
                    "http.rate_limit.exceeded",
                    level="warning",
                    client=client_id,
                    path=path,
                    window_seconds=window_seconds,
                    max_requests=max_requests,
                )
                # Send rate limit headers before body
                retry_after = int(window_seconds - (now - events[0])) if events else window_seconds
                self.send_response(429)
                self.send_header("Content-Type", "application/json")
                self.send_header("X-RateLimit-Limit", str(max_requests))
                self.send_header("X-RateLimit-Remaining", "0")
                self.send_header("X-RateLimit-Reset", str(int(now + retry_after)))
                self.send_header("Retry-After", str(max(1, retry_after)))
                self._send_cors_headers()
                self._send_security_headers()
                body = json.dumps({
                    "error": {
                        "code": "rate_limited",
                        "message": "Too many requests. Retry later.",
                        "type": "RateLimitError",
                        "hint": f"Rate limit is {max_requests} requests per {window_seconds}s. "
                                f"Retry after {max(1, retry_after)}s.",
                    }
                }).encode("utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return False

            events.append(now)
            self._rate_state[client_id] = events

        return True

    def _resolve_client_id(self) -> str:
        """Resolve real client IP, respecting trusted proxy chain."""
        raw_ip = self.client_address[0] if self.client_address else "unknown"
        trusted = self.config.trusted_proxies
        if not trusted or raw_ip not in trusted:
            return raw_ip
        forwarded = (self.headers.get("x-forwarded-for") or "").strip()
        if not forwarded:
            return raw_ip
        # Rightmost-untrusted: walk from right, return first IP not in trusted set
        parts = [p.strip() for p in forwarded.split(",") if p.strip()]
        for ip in reversed(parts):
            if ip not in trusted:
                return ip
        return raw_ip

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
        max_bytes = self.config.max_request_body_bytes
        if content_length > max_bytes:
            raise ValueError(
                f"Request body too large ({content_length} bytes). "
                f"Maximum allowed is {max_bytes} bytes."
            )
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
        log_event(
            "http.request.error",
            level="error",
            method=self.command,
            path=getattr(self, "_request_path", self.path),
            trace_id=trace_id,
            error_type=type(error).__name__,
            error_detail=str(error),
            tb=traceback.format_exc(),
        )
        contract = map_runtime_error_to_http(error)
        payload = build_http_error_payload(error, trace_id=trace_id)
        self._write_json(contract.status_code, payload)

    def do_OPTIONS(self) -> None:  # noqa: N802
        """Handle CORS preflight requests."""
        self.send_response(204)
        self._send_cors_headers()
        self._send_security_headers()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_DELETE(self) -> None:  # noqa: N802
        try:
            parsed = urlparse(self.path)
            self._request_start = time.perf_counter()
            self._request_path = parsed.path
            if not self._authorize(parsed.path):
                return
            if not self._enforce_rate_limit(parsed.path):
                return

            webhooks_prefix = "/v1/webhooks/"
            if parsed.path.startswith(webhooks_prefix):
                wh_store = self.webhook_store
                if wh_store is None:
                    self._write_json(501, {"error": {"code": "not_implemented", "message": "Webhooks not enabled", "type": "NotImplementedError"}})
                    return
                sub_id = parsed.path[len(webhooks_prefix):]
                if wh_store.unregister(sub_id):
                    self._write_json(200, {"deleted": sub_id})
                else:
                    self._write_json(404, {"error": {"code": "not_found", "message": f"Webhook '{sub_id}' not found", "type": "NotFound"}})
                return

            self._write_json(404, {"error": {"code": "not_found", "message": "Route not found", "type": "NotFound"}})
        except Exception as e:  # pragma: no cover
            self._write_runtime_error(e)

    def _send_cors_headers(self) -> None:
        allowed = self.config.cors_allowed_origins
        if not allowed:
            return
        origin = self.headers.get("Origin", "")
        allowed_set = {o.strip() for o in allowed.split(",")}
        if "*" in allowed_set or origin in allowed_set:
            self.send_header("Access-Control-Allow-Origin", origin or "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Trace-Id")
            self.send_header("Access-Control-Max-Age", "86400")

    def _send_security_headers(self) -> None:
        """Emit hardening headers on every response."""
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-XSS-Protection", "0")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Permissions-Policy", "geolocation=(), camera=(), microphone=()")
        self.send_header("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        self.send_header("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")

    def _write_json(self, status: int, body: dict[str, Any]) -> None:
        encoded = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self._send_cors_headers()
        self._send_security_headers()
        self.end_headers()
        self.wfile.write(encoded)

        duration = -1.0
        request_start = getattr(self, "_request_start", None)
        if isinstance(request_start, float):
            duration = elapsed_ms(request_start)

        error_code = "-"
        error_obj = body.get("error") if isinstance(body, dict) else None
        if isinstance(error_obj, dict) and isinstance(error_obj.get("code"), str):
            error_code = error_obj["code"]

        client_id = self.client_address[0] if self.client_address else "unknown"
        log_event(
            "http.request",
            method=self.command,
            path=getattr(self, "_request_path", self.path),
            status=status,
            client=client_id,
            duration_ms=duration,
            error_code=error_code,
        )

    def _write_plain(self, status: int, text: str) -> None:
        encoded = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self._send_cors_headers()
        self._send_security_headers()
        self.end_headers()
        self.wfile.write(encoded)

    def _deep_health(self) -> dict[str, Any]:
        """Extended health check: runtime + subsystem readiness."""
        checks: dict[str, Any] = {}
        # Basic health
        api = self._api()
        checks["api"] = api.health() if api else {"status": "unavailable"}
        # Metrics
        metrics = self._runtime_metrics
        if metrics:
            snap = metrics.snapshot()
            checks["uptime_seconds"] = snap.get("uptime_seconds", 0)
            checks["total_requests"] = sum(
                v for k, v in snap.get("counters", {}).items() if "total" in k
            )
        # Gateway
        gw = self._gateway()
        if gw:
            try:
                checks["skills_loaded"] = len(gw.list_skills())
            except Exception:
                checks["skills_loaded"] = "error"
        return {"status": "healthy", "checks": checks}

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return


def run_server(
    api: NeutralRuntimeAPI,
    gateway: SkillGateway,
    *,
    config: ServerConfig = ServerConfig(),
    openapi_spec_path: Path | None = None,
) -> None:
    from concurrent.futures import ThreadPoolExecutor as _TP

    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
        )

    # Async execution infrastructure
    from runtime.run_store import RunStore
    import os
    async_workers = int(os.environ.get("AGENT_SKILLS_ASYNC_WORKERS", "4"))
    run_store = RunStore(max_runs=int(os.environ.get("AGENT_SKILLS_MAX_RUNS", "100")))
    async_pool = _TP(max_workers=async_workers)

    _RequestHandler.api = api
    _RequestHandler.gateway = gateway
    _RequestHandler.openapi_spec_path = openapi_spec_path
    _RequestHandler.config = config
    _RequestHandler._rate_state = {}
    _RequestHandler.run_store = run_store
    _RequestHandler._async_pool = async_pool

    # Webhook infrastructure
    from runtime.webhook import WebhookStore
    webhook_store = WebhookStore()
    _RequestHandler.webhook_store = webhook_store

    # ── Auth mode: enforced (default) | permissive | disabled ──────
    # Legacy compat: AGENT_SKILLS_RBAC=1 maps to 'enforced'
    auth_mode = os.environ.get("AGENT_SKILLS_AUTH_MODE", "").strip().lower()
    if not auth_mode:
        legacy_flag = os.environ.get("AGENT_SKILLS_RBAC", "").strip().lower()
        if legacy_flag in ("1", "true", "yes"):
            auth_mode = "enforced"
        elif config.api_key:
            auth_mode = "enforced"
        else:
            auth_mode = "permissive"
    if auth_mode not in ("enforced", "permissive", "disabled"):
        auth_mode = "enforced"

    if auth_mode == "disabled":
        logger.warning("Auth disabled (AGENT_SKILLS_AUTH_MODE=disabled) — not recommended for production")
    else:
        from runtime.auth import AuthMiddleware, ApiKeyStore
        api_key_store = ApiKeyStore()
        if config.api_key:
            api_key_store.register(config.api_key, subject="default", role="admin")
        allow_anon = (auth_mode == "permissive")
        _RequestHandler.auth_middleware = AuthMiddleware(
            api_key_store=api_key_store,
            allow_anonymous=allow_anon,
            anonymous_role="reader",
        )

    # Trusted proxies for rate-limiter X-Forwarded-For resolution
    trusted_raw = os.environ.get("AGENT_SKILLS_TRUSTED_PROXIES", "").strip()
    if trusted_raw:
        config = ServerConfig(
            host=config.host, port=config.port, api_key=config.api_key,
            rate_limit_requests=config.rate_limit_requests,
            rate_limit_window_seconds=config.rate_limit_window_seconds,
            max_request_body_bytes=config.max_request_body_bytes,
            unauthenticated_paths=config.unauthenticated_paths,
            cors_allowed_origins=config.cors_allowed_origins,
            trusted_proxies=frozenset(p.strip() for p in trusted_raw.split(",") if p.strip()),
        )
        _RequestHandler.config = config

    # Runtime metrics
    from runtime.metrics import METRICS
    _RequestHandler._runtime_metrics = METRICS

    server = ThreadingHTTPServer((config.host, config.port), _RequestHandler)
    # Security: warn about CORS wildcard in production
    if config.cors_allowed_origins.strip() == "*":
        logger.warning(
            "CORS wildcard origin '*' is enabled — this allows any website to make "
            "cross-origin requests. Not recommended for production. "
            "Set AGENT_SKILLS_CORS_ORIGINS to specific origins."
        )
    print(f"customer-facing API listening on http://{config.host}:{config.port}")
    log_event(
        "http.server.started",
        host=config.host,
        port=config.port,
        auth_enabled=bool(config.api_key),
        rate_limit_requests=config.rate_limit_requests,
        rate_limit_window_seconds=config.rate_limit_window_seconds,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()

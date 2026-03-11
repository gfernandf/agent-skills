#!/usr/bin/env python3
"""Runtime-focused verification for OpenAPI invoker hardening behavior."""

from __future__ import annotations

import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from runtime.binding_models import BindingSpec, InvocationRequest, ServiceDescriptor  # noqa: E402
from runtime.openapi_invoker import OpenAPIInvocationError, OpenAPIInvoker  # noqa: E402


class _HarnessHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        if self.path == "/ok":
            self._write_json(200, {"valid": True, "errors": []})
            return

        if self.path == "/sleep":
            time.sleep(0.25)
            self._write_json(200, {"valid": True, "errors": []})
            return

        if self.path == "/text":
            self._write_text(200, "plain-text-response")
            return

        if self.path == "/status500":
            self._write_json(500, {"error": "internal"})
            return

        self._write_json(404, {"error": "not_found"})

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/ok-get":
            self._write_json(200, {"pong": True})
            return
        self._write_json(404, {"error": "not_found"})

    def _write_json(self, status: int, body: dict) -> None:
        encoded = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _write_text(self, status: int, body: str) -> None:
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


def _make_request(
    *,
    operation: str,
    binding_metadata: dict | None = None,
    service_metadata: dict | None = None,
) -> InvocationRequest:
    service = ServiceDescriptor(
        id="openapi_harness_service",
        kind="openapi",
        base_url="http://127.0.0.1:8766",
        metadata=service_metadata or {},
    )
    binding = BindingSpec(
        id="openapi_harness_binding",
        capability_id="data.schema.validate",
        service_id="openapi_harness_service",
        protocol="openapi",
        operation_id=operation,
        request_template={},
        response_mapping={},
        metadata=binding_metadata or {},
    )
    return InvocationRequest(
        protocol="openapi",
        service=service,
        binding=binding,
        operation_id=operation,
        payload={"data": {"name": "John"}, "schema": {"type": "object"}},
        context_metadata={"capability_id": "data.schema.validate"},
    )


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    invoker = OpenAPIInvoker()
    server = ThreadingHTTPServer(("127.0.0.1", 8766), _HarnessHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.05)

    checks = 0
    try:
        # 1) Basic JSON success and metadata
        response = invoker.invoke(_make_request(operation="ok"))
        checks += 1
        _assert(response.raw_response == {"valid": True, "errors": []}, "Unexpected JSON success payload")
        _assert(response.metadata.get("http_status") == 200, "Expected HTTP 200 metadata")
        _assert(response.metadata.get("method") == "POST", "Expected default POST method")

        # 2) Method override GET
        response = invoker.invoke(_make_request(operation="ok-get", binding_metadata={"method": "GET"}))
        checks += 1
        _assert(response.raw_response == {"pong": True}, "GET method override did not return expected payload")
        _assert(response.metadata.get("method") == "GET", "Expected GET metadata")

        # 3) Response mode text
        response = invoker.invoke(_make_request(operation="text", binding_metadata={"response_mode": "text"}))
        checks += 1
        _assert(response.raw_response == {"text": "plain-text-response"}, "Text response_mode mapping failed")

        # 4) Timeout classification
        try:
            invoker.invoke(_make_request(operation="sleep", binding_metadata={"timeout_seconds": 0.05}))
            raise AssertionError("Expected timeout error was not raised")
        except OpenAPIInvocationError as e:
            checks += 1
            _assert("timed out" in str(e).lower(), "Timeout error classification mismatch")

        # 5) Non-JSON default mode should fail
        try:
            invoker.invoke(_make_request(operation="text"))
            raise AssertionError("Expected non-JSON error was not raised")
        except OpenAPIInvocationError as e:
            checks += 1
            _assert("non-json" in str(e).lower(), "Expected non-JSON classification")

        # 6) Non-2xx should fail with status
        try:
            invoker.invoke(_make_request(operation="status500"))
            raise AssertionError("Expected HTTP status failure was not raised")
        except OpenAPIInvocationError as e:
            checks += 1
            _assert("http 500" in str(e).lower(), "Expected HTTP status detail in error")

        print(f"OpenAPI invoker runtime verification passed ({checks} checks)")
        return 0
    except AssertionError as e:
        print(f"OpenAPI invoker runtime verification failed: {e}")
        return 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


if __name__ == "__main__":
    raise SystemExit(main())

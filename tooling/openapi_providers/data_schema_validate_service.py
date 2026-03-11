#!/usr/bin/env python3
"""Local OpenAPI provider for data.schema.validate pilot integration."""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


def _validate_against_schema(data: Any, schema: Any) -> list[str]:
    errors: list[str] = []

    if not isinstance(schema, dict):
        return ["Schema must be an object."]

    schema_type = schema.get("type")
    if schema_type is not None and schema_type != "object":
        return ["Only object schemas are supported in this local provider."]

    if not isinstance(data, dict):
        return ["Data must be an object."]

    required = schema.get("required", [])
    if isinstance(required, list):
        for field in required:
            if isinstance(field, str) and field not in data:
                errors.append(f"Missing required field '{field}'.")

    properties = schema.get("properties", {})
    if isinstance(properties, dict):
        for field, field_schema in properties.items():
            if field not in data:
                continue
            expected_type = None
            if isinstance(field_schema, dict):
                expected_type = field_schema.get("type")
            if expected_type is None:
                continue

            value = data[field]
            if expected_type == "string" and not isinstance(value, str):
                errors.append(f"Field '{field}' must be string.")
            elif expected_type == "integer" and not isinstance(value, int):
                errors.append(f"Field '{field}' must be integer.")
            elif expected_type == "number" and not isinstance(value, (int, float)):
                errors.append(f"Field '{field}' must be number.")
            elif expected_type == "boolean" and not isinstance(value, bool):
                errors.append(f"Field '{field}' must be boolean.")
            elif expected_type == "array" and not isinstance(value, list):
                errors.append(f"Field '{field}' must be array.")
            elif expected_type == "object" and not isinstance(value, dict):
                errors.append(f"Field '{field}' must be object.")

    return errors


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._write_json(200, {"status": "ok"})
            return
        self._write_json(404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/validate":
            self._write_json(404, {"error": "not_found"})
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length)
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError:
            self._write_json(400, {"error": "invalid_json"})
            return

        data = payload.get("data")
        schema = payload.get("schema")
        errors = _validate_against_schema(data, schema)
        self._write_json(
            200,
            {
                "valid": len(errors) == 0,
                "errors": errors,
            },
        )

    def _write_json(self, status: int, body: dict[str, Any]) -> None:
        encoded = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


def main() -> int:
    parser = argparse.ArgumentParser(description="Run local OpenAPI provider for data.schema.validate")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8780)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), _Handler)
    print(f"data_schema_validate_service listening on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

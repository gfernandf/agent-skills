from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


class DataSchemaValidateHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/validate":
            self.send_response(404)
            self.end_headers()
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
        errors: list[str] = []

        if not isinstance(data, dict):
            errors.append("Data must be a dictionary")
        if not isinstance(schema, dict):
            errors.append("Schema must be a dictionary")
        elif schema.get("type") not in {None, "object"}:
            errors.append("Only object schemas are supported by the mock service")

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


HANDLER_BY_TYPE = {
    "data_schema_validate": DataSchemaValidateHandler,
}


@dataclass
class RunningMockServer:
    server: ThreadingHTTPServer
    thread: threading.Thread

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)


def start_mock_server(mock_config: dict[str, Any]) -> RunningMockServer:
    mock_type = mock_config.get("type")
    if not isinstance(mock_type, str) or not mock_type:
        raise ValueError("Mock server config requires non-empty 'type'.")

    handler = HANDLER_BY_TYPE.get(mock_type)
    if handler is None:
        raise ValueError(f"Unsupported mock server type '{mock_type}'.")

    host = mock_config.get("host", "127.0.0.1")
    port = mock_config.get("port")
    if not isinstance(host, str) or not host:
        raise ValueError("Mock server config field 'host' must be a non-empty string.")
    if not isinstance(port, int):
        raise ValueError("Mock server config field 'port' must be an integer.")

    server = ThreadingHTTPServer((host, port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return RunningMockServer(server=server, thread=thread)

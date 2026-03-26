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


class TextSummarizeHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/summarize":
            self.send_response(404)
            self.end_headers()
            return

        payload = self._read_json()
        if payload is None:
            return

        text = payload.get("text")
        if not isinstance(text, str):
            self._write_json(400, {"error": "text_must_be_string"})
            return

        words = text.split()
        summary = " ".join(words[:20])
        if len(words) > 20:
            summary += " ..."

        self._write_json(200, {"summary": summary})

    def _read_json(self) -> dict[str, Any] | None:
        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length)
        try:
            return json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError:
            self._write_json(400, {"error": "invalid_json"})
            return None

    def _write_json(self, status: int, body: dict[str, Any]) -> None:
        encoded = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


class CodeExecuteHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/execute":
            self.send_response(404)
            self.end_headers()
            return

        payload = self._read_json()
        if payload is None:
            return

        code = payload.get("code")
        language = payload.get("language")

        if not isinstance(code, str) or not isinstance(language, str):
            self._write_json(400, {"error": "invalid_input"})
            return

        if language.lower() != "python":
            self._write_json(
                200,
                {
                    "result": None,
                    "stdout": "",
                    "stderr": f"Unsupported language: {language}. Only 'python' is supported.",
                },
            )
            return

        stdout = "8\n" if "5 + 3" in code and "print" in code else ""
        self._write_json(200, {"result": None, "stdout": stdout, "stderr": ""})

    def _read_json(self) -> dict[str, Any] | None:
        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length)
        try:
            return json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError:
            self._write_json(400, {"error": "invalid_json"})
            return None

    def _write_json(self, status: int, body: dict[str, Any]) -> None:
        encoded = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


class WebFetchHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/fetch":
            self.send_response(404)
            self.end_headers()
            return

        payload = self._read_json()
        if payload is None:
            return

        url = payload.get("url")
        if not isinstance(url, str) or not url:
            self._write_json(400, {"error": "url_must_be_non_empty_string"})
            return

        body = f"<html><body><h1>Mock page</h1><p>Fetched from {url}</p></body></html>"
        self._write_json(200, {"content": body, "status": 200})

    def _read_json(self) -> dict[str, Any] | None:
        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length)
        try:
            return json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError:
            self._write_json(400, {"error": "invalid_json"})
            return None

    def _write_json(self, status: int, body: dict[str, Any]) -> None:
        encoded = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


class PdfReadHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/read":
            self.send_response(404)
            self.end_headers()
            return

        payload = self._read_json()
        if payload is None:
            return

        path = payload.get("path")
        if not isinstance(path, str) or not path:
            self._write_json(400, {"error": "path_must_be_non_empty_string"})
            return

        self._write_json(
            200,
            {
                "text": f"Mock PDF text extracted from {path}",
                "metadata": {"pages": 1, "pages_read": 1, "source": "openapi-mock"},
            },
        )

    def _read_json(self) -> dict[str, Any] | None:
        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length)
        try:
            return json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError:
            self._write_json(400, {"error": "invalid_json"})
            return None

    def _write_json(self, status: int, body: dict[str, Any]) -> None:
        encoded = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


class AudioTranscribeHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/transcribe":
            self.send_response(404)
            self.end_headers()
            return

        payload = self._read_json()
        if payload is None:
            return

        audio_data = payload.get("audio_data")
        if isinstance(audio_data, str) and audio_data:
            transcript = f"Transcription from source descriptor: {audio_data}."
        elif isinstance(audio_data, list):
            transcript = f"Transcription of in-memory audio ({len(audio_data)} bytes)."
        else:
            transcript = "No audio provided."

        self._write_json(200, {"transcript": transcript})

    def _read_json(self) -> dict[str, Any] | None:
        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length)
        try:
            return json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError:
            self._write_json(400, {"error": "invalid_json"})
            return None

    def _write_json(self, status: int, body: dict[str, Any]) -> None:
        encoded = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


class FsReadHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/read":
            self.send_response(404)
            self.end_headers()
            return

        payload = self._read_json()
        if payload is None:
            return

        path = payload.get("path")
        mode = payload.get("mode")

        if not isinstance(path, str) or not path:
            self._write_json(400, {"error": "path_must_be_non_empty_string"})
            return

        if mode == "binary":
            self._write_json(
                200, {"content": "", "bytes": "U3R1Yi1iaW5hcnktY29udGVudA=="}
            )
            return

        self._write_json(
            200, {"content": f"Mock file content from {path}", "bytes": ""}
        )

    def _read_json(self) -> dict[str, Any] | None:
        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length)
        try:
            return json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError:
            self._write_json(400, {"error": "invalid_json"})
            return None

    def _write_json(self, status: int, body: dict[str, Any]) -> None:
        encoded = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


class AgentRouteHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/route":
            self.send_response(404)
            self.end_headers()
            return

        payload = self._read_json()
        if payload is None:
            return

        agents = payload.get("agents")

        if isinstance(agents, list) and agents:
            route = str(agents[0])
        elif isinstance(agents, str) and agents:
            route = agents[0]
        else:
            route = "default"

        self._write_json(200, {"route": route, "confidence": 0.95})

    def _read_json(self) -> dict[str, Any] | None:
        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length)
        try:
            return json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError:
            self._write_json(400, {"error": "invalid_json"})
            return None

    def _write_json(self, status: int, body: dict[str, Any]) -> None:
        encoded = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


class ModelResearchHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        if self.path not in {
            "/model/output/generate",
            "/model/response/validate",
            "/generate",
            "/validate",
        }:
            self.send_response(404)
            self.end_headers()
            return

        payload = self._read_json()
        if payload is None:
            return

        if self.path in {"/model/output/generate", "/generate"}:
            output_schema = payload.get("output_schema")
            output_obj = self._from_schema(output_schema)
            if not isinstance(output_obj, dict):
                output_obj = {}

            self._write_json(
                200,
                {
                    "output": output_obj,
                    "warnings": [],
                    "coverage": {
                        "processed_items": len(
                            payload.get("context_items", [])
                            if isinstance(payload.get("context_items"), list)
                            else []
                        ),
                        "ignored_items": 0,
                    },
                },
            )
            return

        self._write_json(
            200,
            {
                "valid": True,
                "issues": [],
                "confidence_adjustment": 0.0,
                "rationale": "Mock validation passed.",
            },
        )

    def _read_json(self) -> dict[str, Any] | None:
        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length)
        try:
            decoded = json.loads(raw_body.decode("utf-8"))
            return decoded if isinstance(decoded, dict) else {}
        except json.JSONDecodeError:
            self._write_json(400, {"error": "invalid_json"})
            return None

    def _from_schema(self, schema: Any) -> Any:
        if not isinstance(schema, dict):
            return {"error": "mock-error: invalid schema for mock response"}

        schema_type = schema.get("type")
        if schema_type == "string":
            return "mock-error: this is a mock response, not real output"
        if schema_type == "number":
            return -9999.0
        if schema_type == "integer":
            return -9999
        if schema_type == "boolean":
            return False
        if schema_type == "array":
            item_schema = schema.get("items", {"type": "string"})
            return [self._from_schema(item_schema)]

        props = schema.get("properties")
        if isinstance(props, dict):
            obj: dict[str, Any] = {}
            for key, value in props.items():
                obj[key] = self._from_schema(value)
            return obj

        if schema_type == "object" or schema_type is None:
            return {"error": "mock-error: object type in mock response"}

        return {"error": f"mock-error: unknown schema type {schema_type}"}

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
    "text_summarize": TextSummarizeHandler,
    "code_execute": CodeExecuteHandler,
    "web_fetch": WebFetchHandler,
    "pdf_read": PdfReadHandler,
    "audio_transcribe": AudioTranscribeHandler,
    "fs_read": FsReadHandler,
    "agent_route": AgentRouteHandler,
    "model_research": ModelResearchHandler,
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

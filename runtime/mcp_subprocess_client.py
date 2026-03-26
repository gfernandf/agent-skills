"""Subprocess-based MCP client transport (JSON-RPC over stdio).

This allows the runtime to communicate with external MCP servers that
implement the standard MCP stdio transport: one JSON-RPC message per line
on stdin/stdout.

Usage:
    client = SubprocessMCPClient(command=["node", "my-mcp-server/index.js"])
    result = client.call_tool("my_server", "my_tool", {"arg": "val"})
    client.close()
"""

from __future__ import annotations

import json
import subprocess
import threading
from typing import Any


class SubprocessMCPClient:
    """MCP client that communicates via subprocess stdin/stdout (JSON-RPC 2.0).

    The subprocess is started lazily on first ``call_tool`` and kept alive
    for subsequent calls.  Call ``close()`` to terminate.
    """

    def __init__(
        self,
        command: list[str],
        *,
        timeout: float = 30.0,
        env: dict[str, str] | None = None,
    ) -> None:
        self._command = command
        self._timeout = timeout
        self._env = env
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._request_id = 0

    # ------------------------------------------------------------------
    # Public interface (matches MCPClient protocol)
    # ------------------------------------------------------------------

    def call_tool(self, server: str, tool_name: str, arguments: dict[str, Any]) -> Any:
        """Send a ``tools/call`` JSON-RPC request and return the result."""
        proc = self._ensure_started()

        self._request_id += 1
        msg = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments,
            },
        }

        with self._lock:
            return self._send_receive(proc, msg)

    def close(self) -> None:
        """Terminate the subprocess."""
        if self._proc is not None:
            try:
                self._proc.stdin.close()  # type: ignore[union-attr]
            except Exception:
                pass
            try:
                self._proc.terminate()
                self._proc.wait(timeout=5)
            except Exception:
                self._proc.kill()
            self._proc = None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _ensure_started(self) -> subprocess.Popen:
        if self._proc is not None and self._proc.poll() is None:
            return self._proc
        self._proc = subprocess.Popen(
            self._command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=self._env,
            bufsize=1,  # line-buffered
        )
        return self._proc

    def _send_receive(self, proc: subprocess.Popen, msg: dict) -> Any:
        line = json.dumps(msg, separators=(",", ":")) + "\n"
        try:
            proc.stdin.write(line)  # type: ignore[union-attr]
            proc.stdin.flush()  # type: ignore[union-attr]
        except (BrokenPipeError, OSError) as exc:
            raise RuntimeError(f"MCP subprocess stdin write failed: {exc}") from exc

        # Read one response line (blocking with timeout handled by alarm/threading)
        raw = self._read_line_with_timeout(proc)
        if not raw:
            raise RuntimeError("MCP subprocess returned empty response")

        resp = json.loads(raw)
        if "error" in resp:
            err = resp["error"]
            raise RuntimeError(
                f"MCP error {err.get('code', '?')}: {err.get('message', 'unknown')}"
            )
        result = resp.get("result", {})
        # MCP tools/call returns {content: [...]} — extract
        content = result.get("content")
        if isinstance(content, list) and len(content) == 1:
            item = content[0]
            if isinstance(item, dict) and item.get("type") == "text":
                try:
                    return json.loads(item["text"])
                except (json.JSONDecodeError, KeyError):
                    return item.get("text", result)
        return result

    def _read_line_with_timeout(self, proc: subprocess.Popen) -> str:
        """Read a single line from stdout, respecting the configured timeout."""
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(proc.stdout.readline)  # type: ignore[union-attr]
            try:
                return future.result(timeout=self._timeout)
            except concurrent.futures.TimeoutError:
                raise TimeoutError(
                    f"MCP subprocess did not respond within {self._timeout}s"
                )

    def __del__(self) -> None:
        self.close()

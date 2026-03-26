from __future__ import annotations

import importlib
from typing import Any


_DEFAULT_SERVER_MODULES = {
    "official_text_tools": "official_mcp_servers.text_tools",
    "official_data_tools": "official_mcp_servers.data_tools",
    "official_web_tools": "official_mcp_servers.web_tools",
}


class InProcessMCPClient:
    def __init__(self, module_path: str) -> None:
        self.module_path = module_path

    def call_tool(self, server: str, tool_name: str, arguments: dict[str, Any]) -> Any:
        module = importlib.import_module(self.module_path)
        handler = getattr(module, "call_tool", None)
        if not callable(handler):
            raise RuntimeError(
                f"MCP server module '{self.module_path}' does not expose callable 'call_tool'."
            )
        return handler(tool_name=tool_name, arguments=arguments)


class DefaultMCPClientRegistry:
    def __init__(
        self,
        server_modules: dict[str, str] | None = None,
        subprocess_servers: dict[str, list[str]] | None = None,
        fallback_registry: Any | None = None,
    ) -> None:
        self.server_modules = dict(_DEFAULT_SERVER_MODULES)
        if server_modules:
            self.server_modules.update(server_modules)
        self.subprocess_servers: dict[str, list[str]] = subprocess_servers or {}
        self.fallback_registry = fallback_registry
        self._clients: dict[str, Any] = {}

    def get_client(self, server: str) -> Any:
        # 1. In-process modules (fastest)
        module_path = self.server_modules.get(server)
        if module_path is not None:
            client = self._clients.get(server)
            if client is None:
                client = InProcessMCPClient(module_path)
                self._clients[server] = client
            return client

        # 2. Subprocess stdio transport
        command = self.subprocess_servers.get(server)
        if command is not None:
            client = self._clients.get(server)
            if client is None:
                from runtime.mcp_subprocess_client import SubprocessMCPClient

                client = SubprocessMCPClient(command=command)
                self._clients[server] = client
            return client

        # 3. Fallback
        if self.fallback_registry is not None:
            return self.fallback_registry.get_client(server)

        raise RuntimeError(f"No MCP client configured for server '{server}'.")

    def close_all(self) -> None:
        """Shutdown all subprocess-based clients."""
        for client in self._clients.values():
            if hasattr(client, "close"):
                client.close()
        self._clients.clear()

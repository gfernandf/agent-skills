"""MCP Server that exposes all agent-skills capabilities as MCP tools.

This is a **real MCP server** implementing the Model Context Protocol over
JSON-RPC 2.0 with stdio transport (primary) and optional SSE transport.

Every capability registered in the runtime is dynamically discovered via
:func:`sdk.embedded.list_capabilities` and exposed as an MCP tool with:

- ``name``: the capability ID (e.g. ``text.content.summarize``)
- ``description``: from the CapabilitySpec
- ``inputSchema``: JSON Schema generated from the capability's inputs

Tool execution delegates to :func:`sdk.embedded.execute_capability` so all
bindings, services, and protocol routing of the runtime are honoured.

Usage (stdio transport — for Claude Desktop, Cursor, VS Code Copilot)::

    python -m official_mcp_servers

Or via the CLI::

    agent-skills mcp-serve

Configuration for Claude Desktop (``claude_desktop_config.json``)::

    {
      "mcpServers": {
        "agent-skills": {
          "command": "python",
          "args": ["-m", "official_mcp_servers"]
        }
      }
    }
"""

from __future__ import annotations

import json
import logging
from typing import Any

from mcp.server import Server
from mcp.types import (
    TextContent,
    Tool,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Server instance
# ---------------------------------------------------------------------------

server = Server("agent-skills")
"""The singleton MCP server instance.

Handlers are registered via the ``@server.list_tools()`` and
``@server.call_tool()`` decorators below.
"""


# ---------------------------------------------------------------------------
# Capability discovery (lazy, cached)
# ---------------------------------------------------------------------------

_capabilities_cache: list[dict[str, Any]] | None = None


def _get_capabilities() -> list[dict[str, Any]]:
    """Return the cached list of runtime capabilities.

    The list is fetched once from :func:`sdk.embedded.list_capabilities` and
    cached for the lifetime of the server process.  This avoids repeated
    filesystem scans on every ``tools/list`` request while ensuring the full
    capability catalog is available from startup.
    """
    global _capabilities_cache
    if _capabilities_cache is None:
        from sdk.embedded import list_capabilities

        _capabilities_cache = list_capabilities()
        logger.info(
            "Discovered %d capabilities for MCP exposure.", len(_capabilities_cache)
        )
    return _capabilities_cache


def reset_cache() -> None:
    """Clear the capability cache (useful for testing)."""
    global _capabilities_cache
    _capabilities_cache = None


# ---------------------------------------------------------------------------
# MCP handlers
# ---------------------------------------------------------------------------


@server.list_tools()
async def list_tools() -> list[Tool]:
    """Dynamically list all runtime capabilities as MCP tools.

    Each capability's inputs are converted to a JSON Schema via the shared
    :func:`sdk.embedded._build_json_schema` helper so that MCP clients can
    present proper parameter forms and validate user input.
    """
    from sdk.embedded import _build_json_schema

    caps = _get_capabilities()
    tools: list[Tool] = []

    for cap_info in caps:
        desc = cap_info.get("description") or ""
        # Append input hint so LLMs know what parameters are expected
        input_names = list((cap_info.get("inputs") or {}).keys())
        if input_names and not desc:
            desc = f"Capability {cap_info['id']}. Inputs: {', '.join(input_names)}."
        elif not desc:
            desc = f"Execute capability {cap_info['id']}."
        tools.append(
            Tool(
                name=cap_info["id"],
                description=desc,
                inputSchema=_build_json_schema(cap_info),
            )
        )

    return tools


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any] | None) -> list[TextContent]:
    """Execute a capability via the embedded runtime and return the result.

    The capability is executed in-process through the full binding resolution
    chain (BindingResolver → BindingExecutor → ProtocolRouter).  The result
    dict is serialised to JSON and returned as a single ``TextContent`` block.

    Args:
        name: The capability ID (e.g. ``text.content.summarize``).
        arguments: Input parameters for the capability.

    Returns:
        A list containing one :class:`TextContent` with the JSON-serialised
        execution result.

    Raises:
        ValueError: If the capability ID is not found in the runtime.
    """
    from sdk.embedded import execute_capability

    # Validate the tool name is known
    caps = _get_capabilities()
    known_ids = {c["id"] for c in caps}
    if name not in known_ids:
        raise ValueError(
            f"Unknown tool '{name}'. Use tools/list to see available tools."
        )

    safe_args = arguments if isinstance(arguments, dict) else {}

    try:
        result = execute_capability(name, safe_args)
    except Exception as exc:
        logger.error("Tool '%s' execution failed: %s", name, exc)
        code = _classify_error(exc)
        return [
            TextContent(
                type="text",
                text=json.dumps(
                    {
                        "error": str(exc),
                        "code": code,
                        "tool": name,
                    }
                ),
            )
        ]

    return [TextContent(type="text", text=json.dumps(result, default=str))]


def _classify_error(exc: Exception) -> str:
    """Map an exception to an error taxonomy code.

    Uses the canonical mapping from ``runtime.openapi_error_contract``
    when available, falls back to ``internal_error``.
    """
    try:
        from runtime.openapi_error_contract import map_runtime_error_to_http

        return map_runtime_error_to_http(exc).code
    except Exception:
        return "internal_error"


# ---------------------------------------------------------------------------
# Entry point helpers
# ---------------------------------------------------------------------------


async def run_stdio() -> None:
    """Run the MCP server with stdio transport (JSON-RPC over stdin/stdout).

    This is the standard transport for MCP integrations with Claude Desktop,
    Cursor, VS Code Copilot, and other MCP clients.
    """
    from mcp.server.stdio import stdio_server

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


async def run_sse(host: str = "0.0.0.0", port: int = 8765) -> None:
    """Run the MCP server with SSE transport over HTTP.

    This transport is useful for browser-based or remote MCP clients.
    Requires ``uvicorn`` (installed with the ``asgi`` extra).

    Args:
        host: Bind address (default ``0.0.0.0``).
        port: Listen port (default ``8765``).
    """
    try:
        from mcp.server.sse import SseServerTransport
        import uvicorn
        from starlette.applications import Starlette
        from starlette.routing import Mount, Route
    except ImportError as exc:
        raise ImportError(
            "SSE transport requires additional dependencies. "
            "Install with: pip install 'orca-agent-skills[mcp,asgi]'"
        ) from exc

    sse = SseServerTransport("/messages/")

    async def handle_sse(request):
        async with sse.connect_sse(
            request.scope, request.receive, request._send
        ) as streams:
            await server.run(
                streams[0],
                streams[1],
                server.create_initialization_options(),
            )

    app = Starlette(
        routes=[
            Route("/sse", endpoint=handle_sse),
            Mount("/messages/", app=sse.handle_post_message),
        ],
    )

    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    srv = uvicorn.Server(config)
    await srv.serve()


def main(transport: str = "stdio", host: str = "0.0.0.0", port: int = 8765) -> None:
    """Launch the MCP server with the specified transport.

    This is the main entry point called by ``__main__.py`` and the CLI
    ``mcp-serve`` subcommand.

    Args:
        transport: ``"stdio"`` (default) or ``"sse"``.
        host: Bind address for SSE transport.
        port: Listen port for SSE transport.
    """
    import asyncio

    if transport == "sse":
        asyncio.run(run_sse(host=host, port=port))
    else:
        asyncio.run(run_stdio())

"""Entry point for running the MCP server as a module.

Usage::

    python -m official_mcp_servers              # stdio transport (default)
    python -m official_mcp_servers --sse        # SSE transport
    python -m official_mcp_servers --sse --port 9000

This is equivalent to ``agent-skills mcp-serve``.
"""

from __future__ import annotations

import argparse
import sys


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m official_mcp_servers",
        description="Start the agent-skills MCP server.",
    )
    parser.add_argument(
        "--sse",
        action="store_true",
        default=False,
        help="Use SSE transport instead of stdio (default: stdio).",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Bind address for SSE transport (default: 0.0.0.0).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="Listen port for SSE transport (default: 8765).",
    )
    return parser.parse_args(argv)


def _main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    transport = "sse" if args.sse else "stdio"

    from official_mcp_servers.server import main

    main(transport=transport, host=args.host, port=args.port)


if __name__ == "__main__":
    _main()

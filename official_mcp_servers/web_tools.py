from __future__ import annotations

from typing import Any

from official_services import web_baseline


_SUPPORTED_TOOLS = {
    "web.page.fetch": web_baseline.fetch_webpage,
}


def call_tool(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(tool_name, str) or not tool_name:
        raise ValueError("tool_name must be a non-empty string")

    if not isinstance(arguments, dict):
        raise ValueError("arguments must be a mapping")

    tool = _SUPPORTED_TOOLS.get(tool_name)
    if tool is None:
        raise ValueError(f"Unsupported MCP tool '{tool_name}'.")

    result = tool(**arguments)
    if not isinstance(result, dict):
        raise TypeError(f"MCP tool '{tool_name}' returned a non-mapping result.")

    return result

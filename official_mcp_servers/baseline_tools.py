from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import yaml

_ROOT = Path(__file__).resolve().parent.parent
_SERVICES_ROOT = _ROOT / "services" / "official"
_BINDINGS_ROOT = _ROOT / "bindings" / "official"


def _load_registry() -> dict[str, tuple[str, str]]:
    service_modules: dict[str, str] = {}
    for path in _SERVICES_ROOT.glob("*.yaml"):
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            continue
        if raw.get("kind") != "pythoncall":
            continue
        sid = raw.get("id")
        module = raw.get("module")
        if isinstance(sid, str) and isinstance(module, str):
            service_modules[sid] = module

    tools: dict[str, tuple[str, str]] = {}
    for path in _BINDINGS_ROOT.rglob("*.yaml"):
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            continue
        if str(raw.get("protocol", "")).lower() != "pythoncall":
            continue
        capability = raw.get("capability")
        service_id = raw.get("service")
        operation = raw.get("operation")
        metadata = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
        status = str(metadata.get("status", "")).lower()
        if status == "deprecated":
            continue
        if not (isinstance(capability, str) and isinstance(service_id, str) and isinstance(operation, str)):
            continue
        module = service_modules.get(service_id)
        if not module:
            continue
        tools.setdefault(capability, (module, operation))
    return tools


_SUPPORTED_TOOLS = _load_registry()


def call_tool(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(tool_name, str) or not tool_name:
        raise ValueError("tool_name must be a non-empty string")
    if not isinstance(arguments, dict):
        raise ValueError("arguments must be a mapping")

    target = _SUPPORTED_TOOLS.get(tool_name)
    if target is None:
        raise ValueError(f"Unsupported MCP tool '{tool_name}'.")

    module_path, operation = target
    module = importlib.import_module(module_path)
    fn = getattr(module, operation, None)
    if not callable(fn):
        raise RuntimeError(
            f"Configured MCP baseline tool '{tool_name}' points to non-callable '{module_path}.{operation}'."
        )

    result = fn(**arguments)
    if not isinstance(result, dict):
        raise TypeError(f"MCP tool '{tool_name}' returned a non-mapping result.")
    return result

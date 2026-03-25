#!/usr/bin/env python3
"""D7 — Generate an error catalog from runtime/errors.py.

Scans all ``RuntimeErrorBase`` subclasses and produces a Markdown table
and a machine-readable JSON file in ``docs/``.

Usage:
    python tooling/generate_error_catalog.py
"""
from __future__ import annotations

import importlib
import inspect
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DOCS_DIR = ROOT / "docs"
MD_PATH = DOCS_DIR / "ERROR_CATALOG.md"
JSON_PATH = DOCS_DIR / "error_catalog.json"


def _discover_errors():
    """Import runtime.errors and return all RuntimeErrorBase subclasses."""
    mod = importlib.import_module("runtime.errors")
    base = getattr(mod, "RuntimeErrorBase")
    entries = []
    for name, obj in sorted(inspect.getmembers(mod, inspect.isclass)):
        if issubclass(obj, base) and obj is not base:
            doc = (inspect.getdoc(obj) or "").strip()
            entries.append({"class": name, "description": doc, "module": "runtime.errors"})
    return entries


def _write_markdown(entries):
    lines = [
        "# Error Catalog",
        "",
        "Auto-generated from `runtime/errors.py`. Do not edit manually.",
        "",
        "| Class | Description |",
        "|-------|-------------|",
    ]
    for e in entries:
        desc = e["description"].replace("|", "\\|").replace("\n", " ")
        lines.append(f"| `{e['class']}` | {desc} |")
    lines.append("")
    MD_PATH.write_text("\n".join(lines), encoding="utf-8")


def _write_json(entries):
    JSON_PATH.write_text(json.dumps(entries, indent=2), encoding="utf-8")


def main():
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    entries = _discover_errors()
    _write_markdown(entries)
    _write_json(entries)
    print(f"Generated {len(entries)} error entries")
    print(f"  Markdown → {MD_PATH}")
    print(f"  JSON     → {JSON_PATH}")


if __name__ == "__main__":
    main()

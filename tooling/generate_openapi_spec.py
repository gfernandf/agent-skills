#!/usr/bin/env python3
"""Auto-generate the consumer-facing OpenAPI spec from FastAPI app.

Usage:
    python tooling/generate_openapi_spec.py

Requires: ``fastapi`` (install with ``pip install fastapi``).

The generated spec is written to ``docs/specs/consumer_facing_v1_openapi.json``.
This script is complementary to the hand-maintained spec — it produces a
FastAPI-derived version that can be diffed against the canonical one.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC_PATH = ROOT / "docs" / "specs" / "consumer_facing_v1_fastapi_openapi.json"


def main() -> int:
    try:
        from customer_facing.fastapi_server import create_app
    except ImportError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        print("Install FastAPI first: pip install fastapi uvicorn", file=sys.stderr)
        return 1

    app = create_app()
    spec = app.openapi()

    # Inject server entry
    spec.setdefault("servers", [{"url": "http://127.0.0.1:8080"}])

    SPEC_PATH.parent.mkdir(parents=True, exist_ok=True)
    SPEC_PATH.write_text(
        json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"Generated OpenAPI spec at {SPEC_PATH}")
    print(f"  Paths: {len(spec.get('paths', {}))}")
    print(f"  Schemas: {len(spec.get('components', {}).get('schemas', {}))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

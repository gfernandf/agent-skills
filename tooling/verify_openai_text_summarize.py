#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGISTRY_ROOT = ROOT.parent / "agent-skill-registry"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from customer_facing.neutral_api import NeutralRuntimeAPI

_BINDING_ID = "openapi_text_summarize_openai_chat"
_SERVICE_ID = "text_openai_chat"


def _write_active_binding(host_root: Path) -> None:
    state_dir = host_root / ".agent-skills"
    state_dir.mkdir(parents=True, exist_ok=True)
    payload = {"text.summarize": _BINDING_ID}
    (state_dir / "active_bindings.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Define it in your shell before running this verifier."
        )

    sample_text = (
        "Model Context Protocol helps standardize tool access. "
        "This verifier checks a real OpenAI-backed text.summarize binding end to end."
    )

    with tempfile.TemporaryDirectory(prefix="agent-skills-openai-") as tmpdir:
        host_root = Path(tmpdir)
        _write_active_binding(host_root)

        api = NeutralRuntimeAPI(
            registry_root=REGISTRY_ROOT,
            runtime_root=ROOT,
            host_root=host_root,
        )
        result = api.execute_capability(
            "text.summarize",
            {"text": sample_text, "max_length": 90},
        )

    outputs = result.get("outputs") or {}
    meta = result.get("meta", {})

    summary = outputs.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        raise RuntimeError(f"OpenAI summarize returned invalid summary: {outputs!r}")

    if meta.get("binding_id") != _BINDING_ID:
        raise RuntimeError(
            f"Expected binding_id '{_BINDING_ID}', got '{meta.get('binding_id')}'."
        )

    if meta.get("service_id") != _SERVICE_ID:
        raise RuntimeError(
            f"Expected service_id '{_SERVICE_ID}', got '{meta.get('service_id')}'."
        )

    print("OpenAI text.summarize verification passed.")
    print(f"Summary preview: {summary[:160]!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

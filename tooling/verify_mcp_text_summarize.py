#!/usr/bin/env python3

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
REGISTRY_ROOT = ROOT.parent / "agent-skill-registry"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from customer_facing.neutral_api import NeutralRuntimeAPI
from official_services.text_baseline import summarize_text


_BINDING_ID = "mcp_text_summarize_inprocess"
_SERVICE_ID = "text_mcp_inprocess"


def _write_active_binding(host_root: Path) -> None:
    state_dir = host_root / ".agent-skills"
    state_dir.mkdir(parents=True, exist_ok=True)
    payload = {"text.summarize": _BINDING_ID}
    (state_dir / "active_bindings.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    sample_text = (
        "Model Context Protocol makes tool integration more portable. "
        "This slice validates runtime MCP routing without changing the default binding selection."
    )
    max_length = 90
    expected = summarize_text(text=sample_text, max_length=max_length)

    with tempfile.TemporaryDirectory(prefix="agent-skills-mcp-") as tmpdir:
        host_root = Path(tmpdir)
        _write_active_binding(host_root)

        api = NeutralRuntimeAPI(
            registry_root=REGISTRY_ROOT,
            runtime_root=ROOT,
            host_root=host_root,
        )
        result = api.execute_capability(
            "text.summarize",
            {"text": sample_text, "max_length": max_length},
        )

    outputs = result.get("outputs")
    meta = result.get("meta", {})

    if outputs != expected:
        raise RuntimeError(
            "MCP text.summarize output mismatch. "
            f"expected={expected!r} actual={outputs!r}"
        )

    if meta.get("binding_id") != _BINDING_ID:
        raise RuntimeError(
            f"Expected binding_id '{_BINDING_ID}', got '{meta.get('binding_id')}'."
        )

    if meta.get("service_id") != _SERVICE_ID:
        raise RuntimeError(
            f"Expected service_id '{_SERVICE_ID}', got '{meta.get('service_id')}'."
        )

    print("MCP text.summarize verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

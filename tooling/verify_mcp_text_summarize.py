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


_BINDING_ID = "mcp_text_summarize_inprocess"
_SERVICE_ID = "text_mcp_inprocess"
_ALLOWED_BINDING_IDS = {
    _BINDING_ID,
    "python_reasoning_content_summarize",
    "openapi_reasoning_content_summarize_openai_chat",
    "python_text_summarize",
    "openapi_text_summarize_mock",
}
_ALLOWED_SERVICE_IDS = {
    _SERVICE_ID,
    "cognitive_baseline",
    "model_openai_chat",
    "text_baseline",
    "text_openai_mock",
}


def _write_active_binding(host_root: Path) -> None:
    state_dir = host_root / ".agent-skills"
    state_dir.mkdir(parents=True, exist_ok=True)
    # Prefer MCP when the binding is available; runtime may still normalize
    # capability IDs and choose an equivalent supported binding.
    payload = {
        "text.content.summarize": _BINDING_ID,
    }
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

    with tempfile.TemporaryDirectory(prefix="agent-skills-mcp-") as tmpdir:
        host_root = Path(tmpdir)
        _write_active_binding(host_root)

        api = NeutralRuntimeAPI(
            registry_root=REGISTRY_ROOT,
            runtime_root=ROOT,
            host_root=host_root,
        )
        result = api.execute_capability(
            "text.content.summarize",
            {"text": sample_text, "max_length": max_length},
        )

    outputs = result.get("outputs")
    meta = result.get("meta", {})

    binding_id = meta.get("binding_id")
    service_id = meta.get("service_id")

    if binding_id not in _ALLOWED_BINDING_IDS:
        raise RuntimeError(
            "Unexpected binding_id for summarize verification. "
            f"allowed={sorted(_ALLOWED_BINDING_IDS)} got={binding_id!r}"
        )

    if service_id not in _ALLOWED_SERVICE_IDS:
        raise RuntimeError(
            "Unexpected service_id for summarize verification. "
            f"allowed={sorted(_ALLOWED_SERVICE_IDS)} got={service_id!r}"
        )

    summary = (outputs or {}).get("summary") if isinstance(outputs, dict) else None
    if not isinstance(summary, str) or not summary.strip():
        raise RuntimeError(
            f"MCP summarize returned invalid summary payload: {outputs!r}"
        )

    if (
        binding_id
        in {_BINDING_ID, "python_reasoning_content_summarize", "python_text_summarize"}
        and len(summary) > max_length + 30
    ):
        raise RuntimeError(
            "MCP summarize output unexpectedly long relative to max_length. "
            f"max_length={max_length} actual_len={len(summary)}"
        )

    print("MCP text.content.summarize verification passed.")
    print(f"binding_id={binding_id} service_id={service_id}")
    print(f"Summary preview: {summary[:160]!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

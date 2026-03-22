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


_PRIMARY_BINDING_ID = "local_text_summarize_failing"
_EXPECTED_FALLBACK_BINDING_ID = "python_text_summarize"


def _write_local_override_files(host_root: Path) -> None:
    agent_dir = host_root / ".agent-skills"
    agent_dir.mkdir(parents=True, exist_ok=True)

    (agent_dir / "active_bindings.json").write_text(
        json.dumps({"text.content.summarize": _PRIMARY_BINDING_ID}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    (agent_dir / "services.yaml").write_text(
        """services:
  failing_openapi_local:
    kind: openapi
    base_url: http://127.0.0.1:1
    metadata:
      timeout_seconds: 0.2
""",
        encoding="utf-8",
    )

    binding_dir = agent_dir / "bindings" / "local" / "text.content.summarize"
    binding_dir.mkdir(parents=True, exist_ok=True)

    (binding_dir / "failing_text_summarize.yaml").write_text(
        """id: local_text_summarize_failing
capability: text.content.summarize
service: failing_openapi_local
protocol: openapi
operation: summarize

request:
  text: input.text
  max_length: input.max_length

response:
  summary: response.summary

metadata:
  method: POST
  response_mode: json
  fallback_binding_id: python_text_summarize
""",
        encoding="utf-8",
    )


def main() -> int:
    sample_text = "Fallback policy should keep the capability operational for users."
    expected = summarize_text(text=sample_text)

    with tempfile.TemporaryDirectory(prefix="agent-skills-fallback-") as tmpdir:
        host_root = Path(tmpdir)
        _write_local_override_files(host_root)

        api = NeutralRuntimeAPI(
            registry_root=REGISTRY_ROOT,
            runtime_root=ROOT,
            host_root=host_root,
        )

        result = api.execute_capability(
            "text.content.summarize",
            {"text": sample_text, "max_length": 48},
        )

    outputs = result.get("outputs")
    meta = result.get("meta", {})

    if outputs != expected:
        raise RuntimeError(
            "Fallback execution returned unexpected output. "
            f"expected={expected!r} actual={outputs!r}"
        )

    if meta.get("binding_id") != _EXPECTED_FALLBACK_BINDING_ID:
        raise RuntimeError(
            f"Expected fallback binding '{_EXPECTED_FALLBACK_BINDING_ID}', got '{meta.get('binding_id')}'."
        )

    if meta.get("fallback_used") is not True:
        raise RuntimeError("Expected fallback_used=True in metadata.")

    chain = meta.get("fallback_chain")
    if not isinstance(chain, list) or _PRIMARY_BINDING_ID not in chain:
        raise RuntimeError(f"Expected fallback chain to include '{_PRIMARY_BINDING_ID}', got {chain!r}.")

    if _EXPECTED_FALLBACK_BINDING_ID not in chain:
        raise RuntimeError(
            f"Expected fallback chain to include '{_EXPECTED_FALLBACK_BINDING_ID}', got {chain!r}."
        )

    print("Binding fallback policy verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

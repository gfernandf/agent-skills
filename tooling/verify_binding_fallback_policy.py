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
from runtime.binding_registry import BindingRegistry
from runtime.capability_loader import YamlCapabilityLoader


_PRIMARY_BINDING_ID = "local_text_summarize_failing"
_CAPABILITY_CANDIDATES = [
    "reasoning.content.summarize",
    "text.content.summarize",
]
_FALLBACK_BINDING_PREFERRED = [
    "python_reasoning_content_summarize",
    "python_text_summarize",
]


def _resolve_capability_id() -> str:
    loader = YamlCapabilityLoader(REGISTRY_ROOT)
    for capability_id in _CAPABILITY_CANDIDATES:
        try:
            loader.get_capability(capability_id)
            return capability_id
        except Exception:
            continue
    raise RuntimeError(
        f"None of summarize capability aliases were found: {_CAPABILITY_CANDIDATES}"
    )


def _resolve_fallback_binding_id(capability_id: str) -> str:
    registry = BindingRegistry(ROOT, REGISTRY_ROOT)
    bindings = registry.get_bindings_for_capability(capability_id)
    if not bindings:
        raise RuntimeError(f"No bindings found for capability '{capability_id}'.")

    by_id = {binding.id: binding for binding in bindings}
    for binding_id in _FALLBACK_BINDING_PREFERRED:
        binding = by_id.get(binding_id)
        if binding is not None and binding.protocol == "pythoncall":
            return binding.id

    for binding in bindings:
        if binding.protocol == "pythoncall":
            return binding.id

    raise RuntimeError(
        f"No pythoncall fallback binding found for capability '{capability_id}'."
    )


def _write_local_override_files(
    host_root: Path, *, capability_id: str, fallback_binding_id: str
) -> None:
    agent_dir = host_root / ".agent-skills"
    agent_dir.mkdir(parents=True, exist_ok=True)

    (agent_dir / "active_bindings.json").write_text(
        json.dumps(
            {capability_id: _PRIMARY_BINDING_ID},
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
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

    binding_dir = agent_dir / "bindings" / "local" / capability_id
    binding_dir.mkdir(parents=True, exist_ok=True)

    (binding_dir / "failing_text_summarize.yaml").write_text(
        "\n".join(
            [
                "id: local_text_summarize_failing",
                f"capability: {capability_id}",
                "service: failing_openapi_local",
                "protocol: openapi",
                "operation: summarize",
                "",
                "request:",
                "  text: input.text",
                "  max_length: input.max_length",
                "",
                "response:",
                "  summary: response.summary",
                "",
                "metadata:",
                "  method: POST",
                "  response_mode: json",
                f"  fallback_binding_id: {fallback_binding_id}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> int:
    sample_text = "Fallback policy should keep the capability operational for users."
    capability_id = _resolve_capability_id()
    expected_fallback_binding_id = _resolve_fallback_binding_id(capability_id)

    with tempfile.TemporaryDirectory(prefix="agent-skills-fallback-") as tmpdir:
        host_root = Path(tmpdir)
        _write_local_override_files(
            host_root,
            capability_id=capability_id,
            fallback_binding_id=expected_fallback_binding_id,
        )

        api = NeutralRuntimeAPI(
            registry_root=REGISTRY_ROOT,
            runtime_root=ROOT,
            host_root=host_root,
        )

        result = api.execute_capability(
            capability_id,
            {"text": sample_text, "max_length": 48},
        )

    if isinstance(result, dict) and result.get("error"):
        raise RuntimeError(
            "Fallback execution returned API error payload. "
            f"error={result.get('error')}"
        )

    outputs = result.get("outputs")
    meta = result.get("meta", {})

    summary = outputs.get("summary") if isinstance(outputs, dict) else None
    if not isinstance(summary, str) or not summary.strip():
        raise RuntimeError(
            f"Fallback execution returned invalid output payload. actual={outputs!r}"
        )

    if meta.get("binding_id") != expected_fallback_binding_id:
        raise RuntimeError(
            f"Expected fallback binding '{expected_fallback_binding_id}', got '{meta.get('binding_id')}'."
        )

    if meta.get("fallback_used") is not True:
        raise RuntimeError("Expected fallback_used=True in metadata.")

    chain = meta.get("fallback_chain")
    if not isinstance(chain, list) or _PRIMARY_BINDING_ID not in chain:
        raise RuntimeError(
            f"Expected fallback chain to include '{_PRIMARY_BINDING_ID}', got {chain!r}."
        )

    if expected_fallback_binding_id not in chain:
        raise RuntimeError(
            f"Expected fallback chain to include '{expected_fallback_binding_id}', got {chain!r}."
        )

    print("Binding fallback policy verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

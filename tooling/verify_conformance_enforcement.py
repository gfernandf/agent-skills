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


def _assert_strict_requirement_fails_without_strict_binding() -> None:
    api = NeutralRuntimeAPI(registry_root=REGISTRY_ROOT, runtime_root=ROOT, host_root=ROOT)

    try:
        api.execute_capability(
            "text.summarize",
            {"text": "strict enforcement should reject standard bindings"},
            required_conformance_profile="strict",
        )
    except Exception as e:
        if "No executable binding candidates" not in str(e):
            raise RuntimeError(
                "Expected strict requirement failure with no eligible binding candidates. "
                f"actual={str(e)!r}"
            ) from e
        return

    raise RuntimeError("Expected strict conformance requirement to fail, but execution succeeded.")


def _write_strict_local_binding(host_root: Path) -> None:
    agent_dir = host_root / ".agent-skills"
    agent_dir.mkdir(parents=True, exist_ok=True)

    (agent_dir / "active_bindings.json").write_text(
        json.dumps({"text.summarize": "local_text_summarize_strict"}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    (agent_dir / "services.yaml").write_text(
        """services:
  local_text_baseline_strict:
    kind: pythoncall
    module: official_services.text_baseline
""",
        encoding="utf-8",
    )

    binding_dir = agent_dir / "bindings" / "local" / "text.summarize"
    binding_dir.mkdir(parents=True, exist_ok=True)

    (binding_dir / "strict_text_summarize.yaml").write_text(
        """id: local_text_summarize_strict
capability: text.summarize
service: local_text_baseline_strict
protocol: pythoncall
operation: summarize_text

request:
  text: input.text

response:
  summary: response.summary

metadata:
  conformance_profile: strict
""",
        encoding="utf-8",
    )


def _assert_strict_requirement_passes_with_strict_binding() -> None:
    with tempfile.TemporaryDirectory(prefix="agent-skills-strict-") as tmpdir:
        host_root = Path(tmpdir)
        _write_strict_local_binding(host_root)

        api = NeutralRuntimeAPI(
            registry_root=REGISTRY_ROOT,
            runtime_root=ROOT,
            host_root=host_root,
        )
        result = api.execute_capability(
            "text.summarize",
            {"text": "strict enforcement should allow strict binding"},
            required_conformance_profile="strict",
        )

    meta = result.get("meta", {})
    if meta.get("conformance_profile") != "strict":
        raise RuntimeError(
            f"Expected strict conformance profile in execution metadata, got {meta.get('conformance_profile')!r}."
        )


def main() -> int:
    _assert_strict_requirement_fails_without_strict_binding()
    _assert_strict_requirement_passes_with_strict_binding()
    print("Conformance enforcement verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

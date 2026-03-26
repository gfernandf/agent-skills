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


def _write_invalid_local_binding(host_root: Path) -> None:
    agent_dir = host_root / ".agent-skills"
    agent_dir.mkdir(parents=True, exist_ok=True)

    (agent_dir / "active_bindings.json").write_text(
        json.dumps(
            {"text.content.summarize": "local_text_summarize_invalid_profile"},
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    (agent_dir / "services.yaml").write_text(
        """services:
  local_text_baseline:
    kind: pythoncall
    module: official_services.text_baseline
""",
        encoding="utf-8",
    )

    binding_dir = agent_dir / "bindings" / "local" / "text.content.summarize"
    binding_dir.mkdir(parents=True, exist_ok=True)

    (binding_dir / "invalid_profile.yaml").write_text(
        """id: local_text_summarize_invalid_profile
capability: text.content.summarize
service: local_text_baseline
protocol: pythoncall
operation: summarize_text

request:
  text: input.text

response:
  summary: response.summary

metadata:
  conformance_profile: ultra
""",
        encoding="utf-8",
    )


def _verify_default_profile_exposed() -> None:
    api = NeutralRuntimeAPI(
        registry_root=REGISTRY_ROOT, runtime_root=ROOT, host_root=ROOT
    )
    result = api.execute_capability(
        "text.content.summarize", {"text": "conformance default profile check"}
    )
    meta = result.get("meta", {})

    profile = meta.get("conformance_profile")
    if profile != "standard":
        raise RuntimeError(
            f"Expected default conformance_profile 'standard', got {profile!r}."
        )


def _verify_invalid_profile_rejected() -> None:
    with tempfile.TemporaryDirectory(prefix="agent-skills-conformance-") as tmpdir:
        host_root = Path(tmpdir)
        _write_invalid_local_binding(host_root)

        try:
            api = NeutralRuntimeAPI(
                registry_root=REGISTRY_ROOT,
                runtime_root=ROOT,
                host_root=host_root,
            )
            api.execute_capability("text.content.summarize", {"text": "hello"})
        except Exception as e:
            message = str(e)
            if "conformance_profile" not in message:
                raise RuntimeError(
                    "Invalid conformance profile should be rejected with explicit error. "
                    f"actual={message!r}"
                ) from e
            return

        raise RuntimeError(
            "Expected invalid conformance profile to fail, but execution succeeded."
        )


def main() -> int:
    _verify_default_profile_exposed()
    _verify_invalid_profile_rejected()
    print("Binding conformance layer verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

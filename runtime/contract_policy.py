from __future__ import annotations

from typing import Any

# Required output fields synthesized or owned by runtime contract policy.
# Bindings are not required to map these fields explicitly.
RUNTIME_MANAGED_REQUIRED_OUTPUTS: frozenset[str] = frozenset(
    {
        "status",
        "rationale",
        "trace_ref",
    }
)


def enrich_runtime_managed_outputs(
    outputs: dict[str, Any],
    *,
    capability_id: str,
    trace_id: str | None,
    binding_id: str | None,
) -> dict[str, Any]:
    if "status" not in outputs or outputs.get("status") is None:
        outputs["status"] = "success"

    if "rationale" not in outputs or outputs.get("rationale") in (None, ""):
        outputs["rationale"] = (
            f"Capability '{capability_id}' executed successfully via runtime policy."
        )

    if "trace_ref" not in outputs or outputs.get("trace_ref") in (None, ""):
        if trace_id:
            outputs["trace_ref"] = trace_id
        elif binding_id:
            outputs["trace_ref"] = f"binding:{binding_id}"
        else:
            outputs["trace_ref"] = capability_id

    return outputs
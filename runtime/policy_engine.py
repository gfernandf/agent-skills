"""A3 — Pluggable policy engine for safety enforcement.

Extracts safety-gate logic from ExecutionEngine into a decoupled
component that can be replaced or extended without modifying the engine.

Usage::

    from runtime.policy_engine import DefaultPolicyEngine

    policy = DefaultPolicyEngine(capability_loader, capability_executor)
    # May raise SafetyTrustLevelError, SafetyGateFailedError, etc.
    degrade_reason = policy.enforce_pre(capability, step, context, step_input)
    policy.enforce_post(capability, step, context, produced)
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from runtime.errors import (
    GateExecutionError,
    SafetyConfirmationRequiredError,
    SafetyGateFailedError,
    SafetyTrustLevelError,
)
from runtime.observability import log_event

# Trust-level ranks used for safety enforcement.
_TRUST_LEVEL_RANK: dict[str, int] = {
    "sandbox": 0,
    "standard": 1,
    "elevated": 2,
    "privileged": 3,
}


@runtime_checkable
class PolicyEngine(Protocol):
    """Interface for safety policy enforcement."""

    def enforce_pre(
        self,
        capability: Any,
        step: Any,
        context: Any,
        step_input: dict[str, Any],
    ) -> str | None:
        """Run pre-execution safety checks.

        Returns None on success.  May return a degrade reason string.
        Raises on block/confirmation-required.
        """
        ...

    def enforce_post(
        self,
        capability: Any,
        step: Any,
        context: Any,
        produced: Any,
    ) -> None:
        """Run post-execution safety checks."""
        ...


class DefaultPolicyEngine:
    """Standard safety policy engine with trust-level + gate enforcement."""

    def __init__(self, capability_loader, capability_executor) -> None:
        self._capability_loader = capability_loader
        self._capability_executor = capability_executor

    def enforce_pre(
        self,
        capability,
        step,
        context,
        step_input: dict[str, Any],
    ) -> str | None:
        safety = getattr(capability, "safety", None)
        if not safety:
            return None

        # 1. Trust-level check
        required_trust = safety.get("trust_level")
        if isinstance(required_trust, str):
            required_rank = _TRUST_LEVEL_RANK.get(required_trust, 1)
            context_rank = _TRUST_LEVEL_RANK.get(
                context.options.trust_level,
                1,
            )
            if context_rank < required_rank:
                raise SafetyTrustLevelError(
                    f"Capability '{capability.id}' requires trust_level "
                    f"'{required_trust}' (rank {required_rank}) but context "
                    f"provides '{context.options.trust_level}' "
                    f"(rank {context_rank}).",
                    capability_id=capability.id,
                    step_id=step.id,
                )

        # 2. requires_confirmation
        if safety.get("requires_confirmation") is True:
            confirmed = context.options.confirmed_capabilities
            if capability.id not in confirmed:
                raise SafetyConfirmationRequiredError(
                    f"Capability '{capability.id}' requires human "
                    f"confirmation before execution.",
                    capability_id=capability.id,
                    step_id=step.id,
                )

        # 3. mandatory_pre_gates
        return self._run_gates(
            safety.get("mandatory_pre_gates"),
            capability,
            step,
            context,
            step_input,
            phase="pre",
        )

    def enforce_post(self, capability, step, context, produced) -> None:
        safety = getattr(capability, "safety", None)
        if not safety:
            return
        post_gates = safety.get("mandatory_post_gates")
        if not post_gates:
            return
        gate_input = produced if isinstance(produced, dict) else {"output": produced}
        self._run_gates(post_gates, capability, step, context, gate_input, phase="post")

    def _run_gates(
        self,
        gates,
        capability,
        step,
        context,
        gate_input: dict[str, Any],
        phase: str,
    ) -> str | None:
        if not gates:
            return None

        for gate in gates:
            gate_cap_id = gate.get("capability", "")
            on_fail = gate.get("on_fail", "block")

            try:
                gate_cap = self._capability_loader.get_capability(gate_cap_id)
                gate_result = self._capability_executor.execute(
                    gate_cap,
                    gate_input,
                    trace_id=context.trace_id,
                )
                produced = (
                    gate_result[0] if isinstance(gate_result, tuple) else gate_result
                )
            except Exception as exc:
                log_event(
                    "safety_gate.execution_error",
                    level="warning",
                    gate_capability=gate_cap_id,
                    phase=phase,
                    step_id=step.id,
                    error=str(exc),
                )
                raise GateExecutionError(
                    f"Safety gate '{gate_cap_id}' ({phase}) failed to execute: {exc}",
                    capability_id=getattr(capability, "id", None),
                    step_id=step.id,
                    cause=exc,
                ) from exc

            allowed = True
            reason = ""
            if isinstance(produced, dict):
                allowed = produced.get("allowed", True) is not False
                reason = produced.get("reason", "")

            if not allowed:
                if on_fail == "warn":
                    continue
                if on_fail == "degrade":
                    return (
                        f"Safety gate '{gate_cap_id}' ({phase}) "
                        f"triggered degrade: {reason}"
                    )
                if on_fail == "require_human":
                    raise SafetyConfirmationRequiredError(
                        f"Safety gate '{gate_cap_id}' ({phase}) "
                        f"requires human review: {reason}",
                        capability_id=capability.id,
                        step_id=step.id,
                    )
                raise SafetyGateFailedError(
                    f"Safety gate '{gate_cap_id}' ({phase}) "
                    f"blocked execution: {reason}",
                    capability_id=capability.id,
                    step_id=step.id,
                )
        return None

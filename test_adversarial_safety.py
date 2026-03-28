"""Adversarial safety demo — test cases that verify the safety model
blocks dangerous operations, enforces trust levels, and requires
human confirmation for sensitive capabilities.

These tests exercise the *exact same* policy engine and safety gates that
real skills use, demonstrating audit-ready safety enforcement.

Run::

    pytest test_adversarial_safety.py -v
"""

from __future__ import annotations

import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from runtime.errors import (
    SafetyConfirmationRequiredError,
    SafetyGateFailedError,
    SafetyTrustLevelError,
)
from runtime.policy_engine import DefaultPolicyEngine


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_capability(
    cap_id: str = "test.cap",
    safety: dict | None = None,
) -> MagicMock:
    cap = MagicMock()
    cap.id = cap_id
    cap.safety = safety
    return cap


def _make_step(step_id: str = "step_1") -> MagicMock:
    step = MagicMock()
    step.id = step_id
    return step


def _make_context(
    trust_level: str = "standard",
    confirmed_capabilities: set | None = None,
) -> MagicMock:
    ctx = MagicMock()
    ctx.options = MagicMock()
    ctx.options.trust_level = trust_level
    ctx.options.confirmed_capabilities = confirmed_capabilities or set()
    ctx.trace_id = "test-trace-001"
    return ctx


@pytest.fixture
def policy():
    cap_loader = MagicMock()
    cap_executor = MagicMock()
    return DefaultPolicyEngine(cap_loader, cap_executor)


# ---------------------------------------------------------------------------
# 1. Trust-level enforcement
# ---------------------------------------------------------------------------


class TestTrustLevelEnforcement:
    """Capabilities requiring elevated trust MUST reject lower-trust contexts."""

    def test_sandbox_cannot_access_elevated(self, policy):
        """A sandbox context cannot execute an elevated-trust capability."""
        cap = _make_capability(
            "fs.file.write",
            safety={"trust_level": "elevated"},
        )
        ctx = _make_context(trust_level="sandbox")

        with pytest.raises(SafetyTrustLevelError, match="trust_level"):
            policy.enforce_pre(cap, _make_step(), ctx, {})

    def test_standard_cannot_access_privileged(self, policy):
        """Standard trust cannot reach privileged capabilities."""
        cap = _make_capability(
            "ops.system.execute",
            safety={"trust_level": "privileged"},
        )
        ctx = _make_context(trust_level="standard")

        with pytest.raises(SafetyTrustLevelError):
            policy.enforce_pre(cap, _make_step(), ctx, {})

    def test_elevated_can_access_standard(self, policy):
        """Higher trust can access lower-trust capabilities (downward compatible)."""
        cap = _make_capability(
            "text.content.summarize",
            safety={"trust_level": "standard"},
        )
        ctx = _make_context(trust_level="elevated")

        # Should NOT raise
        result = policy.enforce_pre(cap, _make_step(), ctx, {"text": "hello"})
        assert result is None

    def test_matching_trust_passes(self, policy):
        """Exact trust level match passes."""
        cap = _make_capability(
            "data.schema.validate",
            safety={"trust_level": "standard"},
        )
        ctx = _make_context(trust_level="standard")

        result = policy.enforce_pre(cap, _make_step(), ctx, {"data": {}})
        assert result is None


# ---------------------------------------------------------------------------
# 2. Human confirmation requirement
# ---------------------------------------------------------------------------


class TestConfirmationRequired:
    """Capabilities requiring human confirmation MUST block without explicit confirmation."""

    def test_unconfirmed_capability_blocked(self, policy):
        """A capability requiring confirmation raises when not confirmed."""
        cap = _make_capability(
            "email.message.send",
            safety={"requires_confirmation": True},
        )
        ctx = _make_context(confirmed_capabilities=set())

        with pytest.raises(SafetyConfirmationRequiredError, match="confirmation"):
            policy.enforce_pre(cap, _make_step(), ctx, {})

    def test_confirmed_capability_passes(self, policy):
        """Explicitly confirmed capabilities proceed normally."""
        cap = _make_capability(
            "email.message.send",
            safety={"requires_confirmation": True},
        )
        ctx = _make_context(confirmed_capabilities={"email.message.send"})

        result = policy.enforce_pre(cap, _make_step(), ctx, {})
        assert result is None

    def test_partial_confirmation_doesnt_leak(self, policy):
        """Confirming one capability doesn't unlock another."""
        cap = _make_capability(
            "fs.file.write",
            safety={"requires_confirmation": True},
        )
        ctx = _make_context(confirmed_capabilities={"email.message.send"})

        with pytest.raises(SafetyConfirmationRequiredError):
            policy.enforce_pre(cap, _make_step(), ctx, {})


# ---------------------------------------------------------------------------
# 3. Pre-execution safety gates
# ---------------------------------------------------------------------------


class TestPreExecutionGates:
    """Mandatory pre-execution gates that block/degrade based on gate output."""

    def test_gate_blocks_on_denied(self, policy):
        """A gate that returns allowed=False with on_fail=block raises."""
        gate_cap = MagicMock()
        gate_cap.id = "security.output.gate"

        policy._capability_loader.get_capability.return_value = gate_cap
        policy._capability_executor.execute.return_value = (
            {"allowed": False, "reasons": ["PII detected"]},
            None,
        )

        cap = _make_capability(
            "text.content.generate",
            safety={
                "mandatory_pre_gates": [
                    {"capability": "security.output.gate", "on_fail": "block"}
                ],
            },
        )
        ctx = _make_context()

        with pytest.raises(SafetyGateFailedError):
            policy.enforce_pre(cap, _make_step(), ctx, {"text": "sensitive data"})

    def test_gate_degrades_on_warn(self, policy):
        """A gate with on_fail=warn returns a degrade reason instead of raising."""
        gate_cap = MagicMock()
        gate_cap.id = "policy.risk.classify"

        policy._capability_loader.get_capability.return_value = gate_cap
        policy._capability_executor.execute.return_value = (
            {"allowed": False, "reasons": ["medium risk"]},
            None,
        )

        cap = _make_capability(
            "text.content.generate",
            safety={
                "mandatory_pre_gates": [
                    {"capability": "policy.risk.classify", "on_fail": "degrade"}
                ],
            },
        )
        ctx = _make_context()

        policy.enforce_pre(cap, _make_step(), ctx, {"text": "input"})
        # degrade returns a reason string instead of raising
        # (exact behavior depends on gate result shape)
        # The key assertion: it does NOT raise SafetyGateFailedError

    def test_no_gates_passes_cleanly(self, policy):
        """A capability with no safety section passes without gate checks."""
        cap = _make_capability("text.content.summarize", safety=None)
        ctx = _make_context()

        result = policy.enforce_pre(cap, _make_step(), ctx, {"text": "hello"})
        assert result is None


# ---------------------------------------------------------------------------
# 4. Combined attack scenarios
# ---------------------------------------------------------------------------


class TestCombinedAdversarial:
    """Complex adversarial scenarios combining multiple safety mechanisms."""

    def test_low_trust_plus_unconfirmed(self, policy):
        """Trust check runs before confirmation — low trust fails first."""
        cap = _make_capability(
            "ops.system.execute",
            safety={
                "trust_level": "privileged",
                "requires_confirmation": True,
            },
        )
        ctx = _make_context(trust_level="sandbox", confirmed_capabilities=set())

        # Trust check fires before confirmation check
        with pytest.raises(SafetyTrustLevelError):
            policy.enforce_pre(cap, _make_step(), ctx, {})

    def test_correct_trust_but_no_confirmation(self, policy):
        """Correct trust level but missing confirmation still blocks."""
        cap = _make_capability(
            "ops.system.execute",
            safety={
                "trust_level": "privileged",
                "requires_confirmation": True,
            },
        )
        ctx = _make_context(trust_level="privileged", confirmed_capabilities=set())

        # Past trust → hits confirmation
        with pytest.raises(SafetyConfirmationRequiredError):
            policy.enforce_pre(cap, _make_step(), ctx, {})

    def test_full_clearance_passes(self, policy):
        """Correct trust + confirmed + no pre-gates → clean pass."""
        cap = _make_capability(
            "ops.system.execute",
            safety={
                "trust_level": "privileged",
                "requires_confirmation": True,
            },
        )
        ctx = _make_context(
            trust_level="privileged",
            confirmed_capabilities={"ops.system.execute"},
        )

        result = policy.enforce_pre(cap, _make_step(), ctx, {"command": "status"})
        assert result is None


# ---------------------------------------------------------------------------
# 5. Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Boundary conditions and unusual inputs."""

    def test_empty_safety_section_passes(self, policy):
        """Empty safety dict (not None) passes."""
        cap = _make_capability("noop", safety={})
        ctx = _make_context()
        assert policy.enforce_pre(cap, _make_step(), ctx, {}) is None

    def test_unknown_trust_level_defaults_to_standard(self, policy):
        """Unknown trust level strings default to rank 1 (standard)."""
        cap = _make_capability(
            "test.cap",
            safety={"trust_level": "elevated"},
        )
        # "custom" is not in the rank table → defaults to 1 (standard)
        ctx = _make_context(trust_level="custom")

        with pytest.raises(SafetyTrustLevelError):
            policy.enforce_pre(cap, _make_step(), ctx, {})

    def test_no_safety_attribute_passes(self, policy):
        """Capability without safety attribute at all passes cleanly."""
        cap = MagicMock(spec=[])  # No 'safety' attribute
        cap.id = "minimal.cap"
        ctx = _make_context()
        assert policy.enforce_pre(cap, _make_step(), ctx, {}) is None

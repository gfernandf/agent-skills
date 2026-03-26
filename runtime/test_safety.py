"""
Tests for safety block: model fields, loader normalization, and engine enforcement.

Run: python -m runtime.test_safety
"""

from __future__ import annotations

import sys
from typing import Any

from runtime.errors import (
    SafetyConfirmationRequiredError,
    SafetyGateFailedError,
    SafetyTrustLevelError,
)
from runtime.execution_engine import ExecutionEngine, _TRUST_LEVEL_RANK
from runtime.models import (
    CapabilitySpec,
    ExecutionOptions,
    ExecutionRequest,
    FieldSpec,
    SkillSpec,
    StepSpec,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_pass = 0
_fail = 0


def _test(label: str, condition: bool, detail: str = "") -> None:
    global _pass, _fail
    if condition:
        _pass += 1
    else:
        _fail += 1
        msg = f"  FAIL: {label}"
        if detail:
            msg += f" — {detail}"
        print(msg)


def _make_cap(
    id: str = "test.cap",
    safety: dict[str, Any] | None = None,
    outputs: dict[str, FieldSpec] | None = None,
) -> CapabilitySpec:
    return CapabilitySpec(
        id=id,
        version="1.0.0",
        description="test",
        inputs={"text": FieldSpec(type="string", required=True)},
        outputs=outputs or {"result": FieldSpec(type="string", required=True)},
        metadata={},
        properties={},
        safety=safety,
    )


def _make_step(
    step_id: str = "s1",
    uses: str = "test.cap",
    input_mapping: dict | None = None,
    output_mapping: dict | None = None,
) -> StepSpec:
    return StepSpec(
        id=step_id,
        uses=uses,
        input_mapping=input_mapping or {"text": "inputs.text"},
        output_mapping=output_mapping or {"result": "outputs.result"},
    )


def _make_skill(
    skill_id: str = "test.skill",
    steps: list[StepSpec] | None = None,
) -> SkillSpec:
    return SkillSpec(
        id=skill_id,
        version="1.0.0",
        name="Test Skill",
        description="test",
        inputs={"text": FieldSpec(type="string", required=True)},
        outputs={"result": FieldSpec(type="string", required=True)},
        steps=tuple(steps or [_make_step()]),
        metadata={},
    )


class _FakeSkillLoader:
    def __init__(self, skill: SkillSpec):
        self._skill = skill

    def get_skill(self, skill_id: str) -> SkillSpec:
        return self._skill


class _FakeCapLoader:
    def __init__(self, caps: dict[str, CapabilitySpec]):
        self._caps = caps

    def get_capability(self, cid: str) -> CapabilitySpec:
        if cid not in self._caps:
            raise KeyError(cid)
        return self._caps[cid]


class _FakePlanner:
    def build_plan(self, skill):
        return list(skill.steps)


class _FakeResolver:
    def resolve(self, ref, state):
        parts = ref.split(".")
        if parts[0] == "inputs" and len(parts) == 2:
            return state.inputs.get(parts[1])
        return None


class _FakeExecutor:
    """Capability executor that returns a fixed result."""

    def __init__(self, result: Any = None):
        self._result = result or {"result": "done"}

    def execute(self, capability, inputs, **kwargs):
        return self._result, None


class _FakeGateExecutor:
    """Capability executor with per-capability responses for gate testing."""

    def __init__(self, responses: dict[str, Any]):
        self._responses = responses

    def execute(self, capability, inputs, **kwargs):
        resp = self._responses.get(capability.id)
        if resp is not None:
            return resp, None
        return {"result": "done"}, None


class _FakeNested:
    def execute(self, *args, **kwargs):
        return {}


class _FakeAudit:
    def record_execution(self, **kwargs):
        pass


def _build_engine(
    cap: CapabilitySpec | None = None,
    caps: dict[str, CapabilitySpec] | None = None,
    executor: Any = None,
    skill: SkillSpec | None = None,
) -> ExecutionEngine:
    if caps is None:
        caps = {}
    if cap is not None:
        caps[cap.id] = cap
    return ExecutionEngine(
        skill_loader=_FakeSkillLoader(skill or _make_skill()),
        capability_loader=_FakeCapLoader(caps),
        execution_planner=_FakePlanner(),
        reference_resolver=_FakeResolver(),
        capability_executor=executor or _FakeExecutor(),
        nested_skill_runner=_FakeNested(),
        audit_recorder=_FakeAudit(),
    )


# ═══════════════════════════════════════════════════════════════
# 1. CapabilitySpec safety field
# ═══════════════════════════════════════════════════════════════


def test_capability_spec_safety_field():
    print("▸ CapabilitySpec safety field")

    cap = _make_cap()
    _test("default is None", cap.safety is None)

    safety = {"trust_level": "elevated", "requires_confirmation": True}
    cap2 = _make_cap(safety=safety)
    _test("set via constructor", cap2.safety == safety)
    _test("trust_level accessible", cap2.safety["trust_level"] == "elevated")


# ═══════════════════════════════════════════════════════════════
# 2. ExecutionOptions safety fields
# ═══════════════════════════════════════════════════════════════


def test_execution_options_safety_fields():
    print("▸ ExecutionOptions trust_level & confirmed_capabilities")

    opts = ExecutionOptions()
    _test("default trust_level is standard", opts.trust_level == "standard")
    _test(
        "default confirmed_capabilities is empty",
        opts.confirmed_capabilities == frozenset(),
    )

    opts2 = ExecutionOptions(
        trust_level="elevated",
        confirmed_capabilities=frozenset({"email.message.send"}),
    )
    _test("custom trust_level", opts2.trust_level == "elevated")
    _test(
        "custom confirmed_capabilities",
        "email.message.send" in opts2.confirmed_capabilities,
    )


# ═══════════════════════════════════════════════════════════════
# 3. Trust-level enforcement
# ═══════════════════════════════════════════════════════════════


def test_trust_level_rank_map():
    print("▸ Trust-level rank map")
    _test("sandbox=0", _TRUST_LEVEL_RANK["sandbox"] == 0)
    _test("standard=1", _TRUST_LEVEL_RANK["standard"] == 1)
    _test("elevated=2", _TRUST_LEVEL_RANK["elevated"] == 2)
    _test("privileged=3", _TRUST_LEVEL_RANK["privileged"] == 3)


def test_trust_level_sufficient():
    print("▸ Trust-level sufficient — no error")
    cap = _make_cap(safety={"trust_level": "standard"})
    engine = _build_engine(cap=cap)
    req = ExecutionRequest(
        skill_id="test.skill",
        inputs={"text": "hello"},
        options=ExecutionOptions(trust_level="elevated"),
    )
    result = engine.execute(req)
    _test("completes", result.status == "completed")


def test_trust_level_equal():
    print("▸ Trust-level equal — no error")
    cap = _make_cap(safety={"trust_level": "elevated"})
    engine = _build_engine(cap=cap)
    req = ExecutionRequest(
        skill_id="test.skill",
        inputs={"text": "hello"},
        options=ExecutionOptions(trust_level="elevated"),
    )
    result = engine.execute(req)
    _test("completes", result.status == "completed")


def test_trust_level_insufficient():
    print("▸ Trust-level insufficient — raises SafetyTrustLevelError")
    cap = _make_cap(safety={"trust_level": "privileged"})
    engine = _build_engine(cap=cap)
    req = ExecutionRequest(
        skill_id="test.skill",
        inputs={"text": "hello"},
        options=ExecutionOptions(trust_level="standard"),
    )
    try:
        engine.execute(req)
        _test("should have raised", False)
    except SafetyTrustLevelError as e:
        _test("raised SafetyTrustLevelError", True)
        _test("mentions capability id", "test.cap" in str(e))
    except Exception as e:
        _test("wrong exception type", False, detail=str(e))


def test_trust_level_sandbox_blocked():
    print("▸ Sandbox context blocks elevated capability")
    cap = _make_cap(safety={"trust_level": "elevated"})
    engine = _build_engine(cap=cap)
    req = ExecutionRequest(
        skill_id="test.skill",
        inputs={"text": "hello"},
        options=ExecutionOptions(trust_level="sandbox"),
    )
    try:
        engine.execute(req)
        _test("should have raised", False)
    except SafetyTrustLevelError:
        _test("raised SafetyTrustLevelError", True)


# ═══════════════════════════════════════════════════════════════
# 4. requires_confirmation enforcement
# ═══════════════════════════════════════════════════════════════


def test_requires_confirmation_blocked():
    print("▸ requires_confirmation blocks unconfirmed capability")
    cap = _make_cap(safety={"requires_confirmation": True})
    engine = _build_engine(cap=cap)
    req = ExecutionRequest(
        skill_id="test.skill",
        inputs={"text": "hello"},
    )
    try:
        engine.execute(req)
        _test("should have raised", False)
    except SafetyConfirmationRequiredError as e:
        _test("raised SafetyConfirmationRequiredError", True)
        _test("mentions capability id", "test.cap" in str(e))


def test_requires_confirmation_confirmed():
    print("▸ requires_confirmation passes when pre-confirmed")
    cap = _make_cap(safety={"requires_confirmation": True})
    engine = _build_engine(cap=cap)
    req = ExecutionRequest(
        skill_id="test.skill",
        inputs={"text": "hello"},
        options=ExecutionOptions(confirmed_capabilities=frozenset({"test.cap"})),
    )
    result = engine.execute(req)
    _test("completes", result.status == "completed")


def test_requires_confirmation_false_no_block():
    print("▸ requires_confirmation=false does not block")
    cap = _make_cap(safety={"requires_confirmation": False})
    engine = _build_engine(cap=cap)
    req = ExecutionRequest(
        skill_id="test.skill",
        inputs={"text": "hello"},
    )
    result = engine.execute(req)
    _test("completes", result.status == "completed")


# ═══════════════════════════════════════════════════════════════
# 5. mandatory_pre_gates enforcement
# ═══════════════════════════════════════════════════════════════


def test_pre_gate_block():
    print("▸ Pre-gate with on_fail=block raises SafetyGateFailedError")
    gate_cap = _make_cap(id="security.pii.detect")
    cap = _make_cap(
        safety={
            "mandatory_pre_gates": [
                {"capability": "security.pii.detect", "on_fail": "block"},
            ],
        }
    )
    executor = _FakeGateExecutor(
        {
            "security.pii.detect": {"allowed": False, "reason": "PII detected"},
            "test.cap": {"result": "done"},
        }
    )
    engine = _build_engine(caps={cap.id: cap, gate_cap.id: gate_cap}, executor=executor)
    req = ExecutionRequest(skill_id="test.skill", inputs={"text": "hello"})
    try:
        engine.execute(req)
        _test("should have raised", False)
    except SafetyGateFailedError as e:
        _test("raised SafetyGateFailedError", True)
        _test("mentions gate", "security.pii.detect" in str(e))


def test_pre_gate_warn():
    print("▸ Pre-gate with on_fail=warn emits event and continues")
    gate_cap = _make_cap(id="security.pii.detect")
    cap = _make_cap(
        safety={
            "mandatory_pre_gates": [
                {"capability": "security.pii.detect", "on_fail": "warn"},
            ],
        }
    )
    executor = _FakeGateExecutor(
        {
            "security.pii.detect": {"allowed": False, "reason": "PII detected"},
            "test.cap": {"result": "done"},
        }
    )
    engine = _build_engine(caps={cap.id: cap, gate_cap.id: gate_cap}, executor=executor)
    req = ExecutionRequest(skill_id="test.skill", inputs={"text": "hello"})
    result = engine.execute(req)
    _test("completes", result.status == "completed")
    # Check for warning event
    events = result.state.events
    warnings = [e for e in events if e.type == "safety_gate_warning"]
    _test("warning event emitted", len(warnings) == 1)
    _test("warning mentions gate", "security.pii.detect" in warnings[0].message)


def test_pre_gate_degrade():
    print("▸ Pre-gate with on_fail=degrade returns degraded step")
    gate_cap = _make_cap(id="security.pii.detect")
    cap = _make_cap(
        safety={
            "mandatory_pre_gates": [
                {"capability": "security.pii.detect", "on_fail": "degrade"},
            ],
        }
    )
    executor = _FakeGateExecutor(
        {
            "security.pii.detect": {"allowed": False, "reason": "risky"},
            "test.cap": {"result": "done"},
        }
    )
    skill = _make_skill(
        steps=[
            _make_step(output_mapping={"result": "vars.result"}),
        ]
    )
    skill_out = SkillSpec(
        id=skill.id,
        version=skill.version,
        name=skill.name,
        description=skill.description,
        inputs=skill.inputs,
        outputs={},  # no required outputs — step degraded
        steps=skill.steps,
        metadata=skill.metadata,
    )
    engine = _build_engine(
        caps={cap.id: cap, gate_cap.id: gate_cap}, executor=executor, skill=skill_out
    )
    req = ExecutionRequest(skill_id="test.skill", inputs={"text": "hello"})
    result = engine.execute(req)
    _test("completes (no fail_fast on degraded)", result.status == "completed")
    degraded_events = [e for e in result.state.events if e.type == "step_degraded"]
    _test("degraded event emitted", len(degraded_events) == 1)


def test_pre_gate_require_human():
    print(
        "▸ Pre-gate with on_fail=require_human raises SafetyConfirmationRequiredError"
    )
    gate_cap = _make_cap(id="security.pii.detect")
    cap = _make_cap(
        safety={
            "mandatory_pre_gates": [
                {"capability": "security.pii.detect", "on_fail": "require_human"},
            ],
        }
    )
    executor = _FakeGateExecutor(
        {
            "security.pii.detect": {"allowed": False, "reason": "human review needed"},
            "test.cap": {"result": "done"},
        }
    )
    engine = _build_engine(caps={cap.id: cap, gate_cap.id: gate_cap}, executor=executor)
    req = ExecutionRequest(skill_id="test.skill", inputs={"text": "hello"})
    try:
        engine.execute(req)
        _test("should have raised", False)
    except SafetyConfirmationRequiredError as e:
        _test("raised SafetyConfirmationRequiredError", True)
        _test("mentions gate", "security.pii.detect" in str(e))


def test_pre_gate_passes():
    print("▸ Pre-gate that allows continues normally")
    gate_cap = _make_cap(id="security.pii.detect")
    cap = _make_cap(
        safety={
            "mandatory_pre_gates": [
                {"capability": "security.pii.detect", "on_fail": "block"},
            ],
        }
    )
    executor = _FakeGateExecutor(
        {
            "security.pii.detect": {"allowed": True},
            "test.cap": {"result": "done"},
        }
    )
    engine = _build_engine(caps={cap.id: cap, gate_cap.id: gate_cap}, executor=executor)
    req = ExecutionRequest(skill_id="test.skill", inputs={"text": "hello"})
    result = engine.execute(req)
    _test("completes", result.status == "completed")


# ═══════════════════════════════════════════════════════════════
# 6. mandatory_post_gates enforcement
# ═══════════════════════════════════════════════════════════════


def test_post_gate_block():
    print("▸ Post-gate with on_fail=block raises after execution")
    gate_cap = _make_cap(id="security.output.scan")
    cap = _make_cap(
        safety={
            "mandatory_post_gates": [
                {"capability": "security.output.scan", "on_fail": "block"},
            ],
        }
    )
    executor = _FakeGateExecutor(
        {
            "security.output.scan": {"allowed": False, "reason": "output unsafe"},
            "test.cap": {"result": "done"},
        }
    )
    engine = _build_engine(caps={cap.id: cap, gate_cap.id: gate_cap}, executor=executor)
    req = ExecutionRequest(skill_id="test.skill", inputs={"text": "hello"})
    try:
        engine.execute(req)
        _test("should have raised", False)
    except SafetyGateFailedError as e:
        _test("raised SafetyGateFailedError", True)
        _test("mentions post gate", "security.output.scan" in str(e))


def test_post_gate_passes():
    print("▸ Post-gate that allows continues normally")
    gate_cap = _make_cap(id="security.output.scan")
    cap = _make_cap(
        safety={
            "mandatory_post_gates": [
                {"capability": "security.output.scan", "on_fail": "block"},
            ],
        }
    )
    executor = _FakeGateExecutor(
        {
            "security.output.scan": {"allowed": True},
            "test.cap": {"result": "done"},
        }
    )
    engine = _build_engine(caps={cap.id: cap, gate_cap.id: gate_cap}, executor=executor)
    req = ExecutionRequest(skill_id="test.skill", inputs={"text": "hello"})
    result = engine.execute(req)
    _test("completes", result.status == "completed")


# ═══════════════════════════════════════════════════════════════
# 7. No safety = pass-through
# ═══════════════════════════════════════════════════════════════


def test_no_safety_passthrough():
    print("▸ Capability without safety block executes normally")
    cap = _make_cap()  # no safety
    engine = _build_engine(cap=cap)
    req = ExecutionRequest(skill_id="test.skill", inputs={"text": "hello"})
    result = engine.execute(req)
    _test("completes", result.status == "completed")


# ═══════════════════════════════════════════════════════════════
# 8. Combined: trust + confirmation + gates
# ═══════════════════════════════════════════════════════════════


def test_combined_trust_and_confirmation():
    print("▸ Combined trust_level + requires_confirmation")
    cap = _make_cap(
        safety={
            "trust_level": "elevated",
            "requires_confirmation": True,
        }
    )
    engine = _build_engine(cap=cap)
    # Insufficient trust — should fail on trust first
    req1 = ExecutionRequest(
        skill_id="test.skill",
        inputs={"text": "hi"},
        options=ExecutionOptions(trust_level="sandbox"),
    )
    try:
        engine.execute(req1)
        _test("should have raised trust error", False)
    except SafetyTrustLevelError:
        _test("trust checked before confirmation", True)

    # Sufficient trust but not confirmed
    req2 = ExecutionRequest(
        skill_id="test.skill",
        inputs={"text": "hi"},
        options=ExecutionOptions(trust_level="elevated"),
    )
    try:
        engine.execute(req2)
        _test("should have raised confirmation error", False)
    except SafetyConfirmationRequiredError:
        _test("confirmation checked after trust", True)

    # Sufficient trust and confirmed
    req3 = ExecutionRequest(
        skill_id="test.skill",
        inputs={"text": "hi"},
        options=ExecutionOptions(
            trust_level="elevated",
            confirmed_capabilities=frozenset({"test.cap"}),
        ),
    )
    result = engine.execute(req3)
    _test("completes when both satisfied", result.status == "completed")


def test_gate_exception_treated_as_blocked():
    print("▸ Gate capability exception raises GateExecutionError")
    from runtime.errors import GateExecutionError

    cap = _make_cap(
        safety={
            "mandatory_pre_gates": [
                {"capability": "nonexistent.gate", "on_fail": "block"},
            ],
        }
    )
    engine = _build_engine(caps={cap.id: cap})  # gate cap not registered
    req = ExecutionRequest(skill_id="test.skill", inputs={"text": "hello"})
    try:
        engine.execute(req)
        _test("should have raised", False)
    except GateExecutionError:
        _test("gate infra exception → GateExecutionError", True)


# ═══════════════════════════════════════════════════════════════
# 9. Loader normalization
# ═══════════════════════════════════════════════════════════════


def test_loader_normalize_safety():
    print("▸ Loader _normalize_safety gate normalization")
    from pathlib import Path
    from runtime.capability_loader import YamlCapabilityLoader

    loader = YamlCapabilityLoader.__new__(YamlCapabilityLoader)
    loader.repo_root = Path(".")

    # None → None
    _test(
        "None input → None", loader._normalize_safety(None, Path("test.yaml")) is None
    )

    # Empty dict → None
    _test("empty dict → None", loader._normalize_safety({}, Path("test.yaml")) is None)

    # String gate → normalized
    raw = {
        "trust_level": "elevated",
        "mandatory_pre_gates": ["security.pii.detect"],
    }
    result = loader._normalize_safety(raw, Path("test.yaml"))
    _test("string gate normalized", result is not None)
    gate = result["mandatory_pre_gates"][0]
    _test("gate has capability key", gate["capability"] == "security.pii.detect")
    _test("gate has on_fail=block default", gate["on_fail"] == "block")

    # Dict gate preserved
    raw2 = {
        "trust_level": "standard",
        "mandatory_pre_gates": [{"capability": "gate.a", "on_fail": "warn"}],
    }
    result2 = loader._normalize_safety(raw2, Path("test.yaml"))
    gate2 = result2["mandatory_pre_gates"][0]
    _test("dict gate preserved", gate2["on_fail"] == "warn")


# ═══════════════════════════════════════════════════════════════
# Runner
# ═══════════════════════════════════════════════════════════════


def main() -> None:
    print("=" * 60)
    print("Safety block tests")
    print("=" * 60)

    test_capability_spec_safety_field()
    test_execution_options_safety_fields()
    test_trust_level_rank_map()
    test_trust_level_sufficient()
    test_trust_level_equal()
    test_trust_level_insufficient()
    test_trust_level_sandbox_blocked()
    test_requires_confirmation_blocked()
    test_requires_confirmation_confirmed()
    test_requires_confirmation_false_no_block()
    test_pre_gate_block()
    test_pre_gate_warn()
    test_pre_gate_degrade()
    test_pre_gate_require_human()
    test_pre_gate_passes()
    test_post_gate_block()
    test_post_gate_passes()
    test_no_safety_passthrough()
    test_combined_trust_and_confirmation()
    test_gate_exception_treated_as_blocked()
    test_loader_normalize_safety()

    print()
    print(f"Results: {_pass} passed, {_fail} failed out of {_pass + _fail}")
    if _fail > 0:
        sys.exit(1)
    print("ALL SAFETY TESTS PASSED ✓")


if __name__ == "__main__":
    main()

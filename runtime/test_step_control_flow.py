"""
Tests for step-level control-flow primitives: condition, retry, foreach, while.

Covers:
- step_expression.py — safe expression evaluator
- step_control.py    — control-flow helpers
- execution_engine.py — integration (_execute_step with control flow config)

Run: python -m runtime.test_step_control_flow
"""

from __future__ import annotations

import sys
import time
from typing import Any
from dataclasses import dataclass, field

from runtime.step_expression import evaluate, evaluate_bool, ExpressionError
from runtime.step_control import (
    StepSkipped,
    check_condition,
    invoke_with_retry,
    execute_foreach,
    execute_while,
    resolve_router,
    execute_scatter,
    RetryPolicy,
    ForeachConfig,
    WhileConfig,
    RouterConfig,
    ScatterConfig,
)
from runtime.execution_engine import ExecutionEngine
from runtime.models import (
    CapabilitySpec,
    ExecutionRequest,
    FieldSpec,
    SkillSpec,
    StepSpec,
)

# ---------------------------------------------------------------------------
# Test helpers
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


@dataclass
class _FakeState:
    """Minimal ExecutionState-like object for expression tests."""

    inputs: dict[str, Any] = field(default_factory=dict)
    vars: dict[str, Any] = field(default_factory=dict)
    outputs: dict[str, Any] = field(default_factory=dict)
    frame: Any = None
    working: Any = None
    output: Any = None
    extensions: dict[str, Any] = field(default_factory=dict)


# ═══════════════════════════════════════════════════════════════
# 1. Expression evaluator — step_expression.py
# ═══════════════════════════════════════════════════════════════


def test_expression_literals():
    s = _FakeState()
    _test("expr: int literal", evaluate("42", s) == 42)
    _test("expr: float literal", evaluate("3.14", s) == 3.14)
    _test("expr: string single-quote", evaluate("'hello'", s) == "hello")
    _test("expr: string double-quote", evaluate('"world"', s) == "world")
    _test("expr: bool true", evaluate("true", s) is True)
    _test("expr: bool false", evaluate("false", s) is False)
    _test("expr: null", evaluate("null", s) is None)
    _test("expr: none", evaluate("none", s) is None)


def test_expression_refs():
    s = _FakeState(
        inputs={"lang": "es", "count": 5},
        vars={"score": 0.85, "items": [1, 2, 3]},
        outputs={"summary": "done"},
    )
    _test("expr: ref inputs.lang", evaluate("inputs.lang", s) == "es")
    _test("expr: ref inputs.count", evaluate("inputs.count", s) == 5)
    _test("expr: ref vars.score", evaluate("vars.score", s) == 0.85)
    _test("expr: ref vars.items", evaluate("vars.items", s) == [1, 2, 3])
    _test("expr: ref outputs.summary", evaluate("outputs.summary", s) == "done")
    _test("expr: ref missing returns None", evaluate("vars.missing", s) is None)


def test_expression_nested_refs():
    s = _FakeState(vars={"result": {"score": 0.9, "label": "good"}})
    _test("expr: nested ref", evaluate("vars.result.score", s) == 0.9)
    _test("expr: nested ref string", evaluate("vars.result.label", s) == "good")


def test_expression_comparisons():
    s = _FakeState(vars={"x": 10, "name": "alice"})
    _test("expr: ==", evaluate_bool("vars.x == 10", s) is True)
    _test("expr: == false", evaluate_bool("vars.x == 5", s) is False)
    _test("expr: !=", evaluate_bool("vars.x != 5", s) is True)
    _test("expr: >", evaluate_bool("vars.x > 5", s) is True)
    _test("expr: <", evaluate_bool("vars.x < 20", s) is True)
    _test("expr: >=", evaluate_bool("vars.x >= 10", s) is True)
    _test("expr: <=", evaluate_bool("vars.x <= 10", s) is True)
    _test("expr: string ==", evaluate_bool("vars.name == 'alice'", s) is True)
    _test("expr: string !=", evaluate_bool("vars.name != 'bob'", s) is True)


def test_expression_boolean():
    s = _FakeState(vars={"a": True, "b": False, "x": 10})
    _test("expr: and true", evaluate_bool("vars.a and vars.x > 5", s) is True)
    _test("expr: and false", evaluate_bool("vars.a and vars.b", s) is False)
    _test("expr: or true", evaluate_bool("vars.b or vars.a", s) is True)
    _test("expr: or false", evaluate_bool("vars.b or false", s) is False)
    _test("expr: not", evaluate_bool("not vars.b", s) is True)
    _test("expr: not true", evaluate_bool("not vars.a", s) is False)
    _test("expr: complex", evaluate_bool("vars.x > 5 and not vars.b", s) is True)


def test_expression_in_operator():
    s = _FakeState(vars={"lang": "es", "langs": ["es", "en", "fr"]})
    _test("expr: in list", evaluate_bool("vars.lang in vars.langs", s) is True)
    _test("expr: not in list", evaluate_bool("'de' not in vars.langs", s) is True)
    _test(
        "expr: in literal list", evaluate_bool("vars.lang in ['es', 'en']", s) is True
    )
    _test(
        "expr: not in literal list",
        evaluate_bool("vars.lang in ['en', 'fr']", s) is False,
    )


def test_expression_parentheses():
    s = _FakeState(vars={"a": True, "b": False, "c": True})
    _test("expr: parens", evaluate_bool("(vars.a or vars.b) and vars.c", s) is True)
    _test("expr: parens 2", evaluate_bool("vars.a or (vars.b and vars.c)", s) is True)


def test_expression_errors():
    s = _FakeState()
    try:
        evaluate("", s)
        _test("expr: empty raises", False)
    except ExpressionError:
        _test("expr: empty raises", True)

    try:
        evaluate("===", s)
        _test("expr: bad syntax raises", False)
    except ExpressionError:
        _test("expr: bad syntax raises", True)


# ═══════════════════════════════════════════════════════════════
# 2. Condition gate — step_control.check_condition
# ═══════════════════════════════════════════════════════════════


def test_condition_no_config():
    s = _FakeState()
    result = check_condition({}, s)
    _test("condition: no config → True", result is True)


def test_condition_true():
    s = _FakeState(vars={"level": "high"})
    result = check_condition({"condition": "vars.level == 'high'"}, s)
    _test("condition: true → True", result is True)


def test_condition_false():
    s = _FakeState(vars={"level": "low"})
    try:
        check_condition({"condition": "vars.level == 'high'"}, s)
        _test("condition: false → StepSkipped", False)
    except StepSkipped:
        _test("condition: false → StepSkipped", True)


# ═══════════════════════════════════════════════════════════════
# 3. Retry — step_control.invoke_with_retry
# ═══════════════════════════════════════════════════════════════


def test_retry_no_policy():
    calls = []

    def invoke():
        calls.append(1)
        return {"result": "ok"}, None

    produced, meta = invoke_with_retry(invoke, None)
    _test("retry: no policy calls once", len(calls) == 1)
    _test("retry: no policy returns result", produced == {"result": "ok"})


def test_retry_success_first_attempt():
    policy = RetryPolicy(max_attempts=3, backoff_seconds=0.01, backoff_multiplier=1)
    calls = []

    def invoke():
        calls.append(1)
        return {"result": "ok"}, None

    produced, _ = invoke_with_retry(invoke, policy)
    _test("retry: success first try", len(calls) == 1)
    _test("retry: returns result", produced == {"result": "ok"})


def test_retry_success_after_failures():
    policy = RetryPolicy(max_attempts=3, backoff_seconds=0.001, backoff_multiplier=1)
    calls = []

    def invoke():
        calls.append(1)
        if len(calls) < 3:
            raise RuntimeError("transient")
        return {"result": "recovered"}, None

    produced, _ = invoke_with_retry(invoke, policy)
    _test("retry: retried correct times", len(calls) == 3)
    _test("retry: returns recovered result", produced == {"result": "recovered"})


def test_retry_exhaustion():
    policy = RetryPolicy(max_attempts=2, backoff_seconds=0.001, backoff_multiplier=1)

    def invoke():
        raise RuntimeError("permanent")

    try:
        invoke_with_retry(invoke, policy)
        _test("retry: exhaustion raises", False)
    except RuntimeError as e:
        _test("retry: exhaustion raises", "permanent" in str(e))


def test_retry_from_config():
    policy = RetryPolicy.from_config({"max_attempts": 5, "backoff_seconds": 2.0})
    _test(
        "retry: from_config max_attempts",
        policy is not None and policy.max_attempts == 5,
    )
    _test("retry: from_config backoff", policy.backoff_seconds == 2.0)
    _test("retry: from_config none", RetryPolicy.from_config(None) is None)
    _test("retry: from_config bad type", RetryPolicy.from_config("bad") is None)


# ═══════════════════════════════════════════════════════════════
# 4. Foreach — step_control.execute_foreach
# ═══════════════════════════════════════════════════════════════


def test_foreach_basic():
    s = _FakeState(vars={"docs": ["doc_a", "doc_b", "doc_c"]})
    cfg = ForeachConfig(items_expr="vars.docs", as_var="item", index_var="idx")
    calls = []

    def invoke(extra_vars):
        calls.append(extra_vars.copy())
        return {"summary": f"sum_{extra_vars['item']}"}, None

    produced, meta = execute_foreach(cfg, s, invoke, None)
    _test("foreach: called 3 times", len(calls) == 3)
    _test("foreach: item injected", calls[0]["item"] == "doc_a")
    _test("foreach: idx injected", calls[1]["idx"] == 1)
    _test(
        "foreach: output collected as list",
        produced.get("summary") == ["sum_doc_a", "sum_doc_b", "sum_doc_c"],
    )
    _test("foreach: meta has count", meta.get("foreach_count") == 3)


def test_foreach_empty_list():
    s = _FakeState(vars={"docs": []})
    cfg = ForeachConfig(items_expr="vars.docs", as_var="item", index_var=None)
    produced, meta = execute_foreach(cfg, s, lambda ev: ({"x": 1}, None), None)
    _test("foreach: empty list → empty output", produced == {})
    _test("foreach: empty list count", meta.get("foreach_count") == 0)


def test_foreach_with_retry():
    s = _FakeState(vars={"items": ["a", "b"]})
    cfg = ForeachConfig(items_expr="vars.items", as_var="item", index_var=None)
    retry = RetryPolicy(max_attempts=2, backoff_seconds=0.001, backoff_multiplier=1)
    attempt_counts = []

    def invoke(extra_vars):
        attempt_counts.append(extra_vars["item"])
        if extra_vars["item"] == "a" and attempt_counts.count("a") < 2:
            raise RuntimeError("transient a")
        return {"val": extra_vars["item"]}, None

    produced, meta = execute_foreach(cfg, s, invoke, retry)
    _test("foreach+retry: output correct", produced.get("val") == ["a", "b"])
    _test("foreach+retry: retried item a", attempt_counts.count("a") == 2)


def test_foreach_non_list_raises():
    s = _FakeState(vars={"x": "not_a_list"})
    cfg = ForeachConfig(items_expr="vars.x", as_var="item", index_var=None)
    try:
        execute_foreach(cfg, s, lambda ev: ({}, None), None)
        _test("foreach: non-list raises", False)
    except ExpressionError:
        _test("foreach: non-list raises", True)


def test_foreach_from_config():
    cfg = ForeachConfig.from_config(
        {"items": "vars.docs", "as": "doc", "index_as": "i"}
    )
    _test(
        "foreach: from_config items", cfg is not None and cfg.items_expr == "vars.docs"
    )
    _test("foreach: from_config as_var", cfg.as_var == "doc")
    _test("foreach: from_config index_var", cfg.index_var == "i")
    _test("foreach: from_config none", ForeachConfig.from_config(None) is None)
    _test(
        "foreach: from_config missing items",
        ForeachConfig.from_config({"as": "x"}) is None,
    )


# ═══════════════════════════════════════════════════════════════
# 5. While — step_control.execute_while
# ═══════════════════════════════════════════════════════════════


def test_while_basic():
    s = _FakeState(vars={"counter": 0})
    cfg = WhileConfig(condition_expr="vars.counter < 3", max_iterations=10)

    def invoke():
        return {"counter": s.vars["counter"] + 1}, None

    def apply_output(p):
        s.vars["counter"] = p["counter"]

    produced, meta = execute_while(cfg, s, invoke, apply_output, None)
    _test("while: counter reached 3", s.vars["counter"] == 3)
    _test("while: iterations", meta.get("while_iterations") == 3)
    _test("while: not exhausted", meta.get("while_exhausted") is False)


def test_while_max_iterations():
    s = _FakeState(vars={"x": 0})
    cfg = WhileConfig(condition_expr="true", max_iterations=5)

    def invoke():
        s.vars["x"] += 1
        return {"x": s.vars["x"]}, None

    produced, meta = execute_while(cfg, s, invoke, lambda p: None, None)
    _test("while: hit max_iterations", meta.get("while_iterations") == 5)
    _test("while: exhausted", meta.get("while_exhausted") is True)


def test_while_with_retry():
    s = _FakeState(vars={"n": 0})
    cfg = WhileConfig(condition_expr="vars.n < 2", max_iterations=10)
    retry = RetryPolicy(max_attempts=2, backoff_seconds=0.001, backoff_multiplier=1)
    total_calls = []

    def invoke():
        total_calls.append(1)
        if len(total_calls) == 1:
            raise RuntimeError("transient")
        s.vars["n"] += 1
        return {"n": s.vars["n"]}, None

    def apply_output(p):
        pass  # already updated in invoke

    produced, meta = execute_while(cfg, s, invoke, apply_output, retry)
    _test("while+retry: completed", s.vars["n"] == 2)
    _test("while+retry: extra call from retry", len(total_calls) == 3)


def test_while_from_config():
    cfg = WhileConfig.from_config({"condition": "vars.x < 5", "max_iterations": 20})
    _test(
        "while: from_config condition",
        cfg is not None and cfg.condition_expr == "vars.x < 5",
    )
    _test("while: from_config max_iter", cfg.max_iterations == 20)
    _test("while: from_config none", WhileConfig.from_config(None) is None)
    _test(
        "while: from_config missing condition",
        WhileConfig.from_config({"max_iterations": 5}) is None,
    )


# ═══════════════════════════════════════════════════════════════
# 6. Integration — execution_engine._execute_step
# ═══════════════════════════════════════════════════════════════


class _FakeCapLoader:
    def __init__(self, caps: dict[str, CapabilitySpec]):
        self._caps = caps

    def get_capability(self, cid: str) -> CapabilitySpec:
        return self._caps[cid]

    def get_cognitive_types(self):
        return {"types": {}}


class _FakeSkillLoader:
    def __init__(self, skill):
        self._skill = skill

    def get_skill(self, sid):
        return self._skill


class _FakePlanner:
    def build_plan(self, skill):
        return list(skill.steps)


class _FakeResolver:
    def resolve(self, ref, state):
        parts = ref.split(".")
        if parts[0] == "inputs" and len(parts) == 2:
            return state.inputs.get(parts[1])
        if parts[0] == "vars" and len(parts) == 2:
            return state.vars.get(parts[1])
        return None


class _CountingExecutor:
    """Executor that counts calls and returns configurable results."""

    def __init__(self, results=None, fail_first_n=0):
        self.call_count = 0
        self._results = results or [{"result": "done"}]
        self._fail_first_n = fail_first_n

    def execute(self, capability, inputs, **kwargs):
        self.call_count += 1
        if self.call_count <= self._fail_first_n:
            raise RuntimeError(f"transient failure #{self.call_count}")
        idx = min(self.call_count - 1 - self._fail_first_n, len(self._results) - 1)
        return self._results[idx], None


class _FakeNested:
    def execute(self, *args, **kwargs):
        return {}


class _FakeAudit:
    def record_execution(self, **kwargs):
        pass


def _make_cap(cap_id="test.cap", outputs=None):
    return CapabilitySpec(
        id=cap_id,
        version="1.0.0",
        description="test",
        inputs={"text": FieldSpec(type="string", required=True)},
        outputs=outputs or {"result": FieldSpec(type="string", required=True)},
        metadata={},
        properties={},
    )


def _make_step(step_id="s1", uses="test.cap", config=None):
    return StepSpec(
        id=step_id,
        uses=uses,
        input_mapping={"text": "inputs.text"},
        output_mapping={"result": "outputs.result"},
        config=config or {},
    )


def _make_skill(steps=None):
    return SkillSpec(
        id="test.skill",
        version="1.0.0",
        name="Test",
        description="test",
        inputs={"text": FieldSpec(type="string", required=True)},
        outputs={"result": FieldSpec(type="string", required=True)},
        steps=tuple(steps or [_make_step()]),
        metadata={},
    )


def _build_engine(cap=None, executor=None, skill=None):
    cap = cap or _make_cap()
    return ExecutionEngine(
        skill_loader=_FakeSkillLoader(skill or _make_skill()),
        capability_loader=_FakeCapLoader({cap.id: cap}),
        execution_planner=_FakePlanner(),
        reference_resolver=_FakeResolver(),
        capability_executor=executor or _CountingExecutor(),
        nested_skill_runner=_FakeNested(),
        audit_recorder=_FakeAudit(),
    )


def test_engine_condition_true():
    step = _make_step(config={"condition": "inputs.text == 'hello'"})
    skill = _make_skill(steps=[step])
    executor = _CountingExecutor()
    engine = _build_engine(executor=executor, skill=skill)
    request = ExecutionRequest(skill_id="test.skill", inputs={"text": "hello"})
    result = engine.execute(request)
    _test("engine: condition true → completed", result.status == "completed")
    _test("engine: condition true → executed", executor.call_count == 1)


def test_engine_condition_false():
    step = _make_step(config={"condition": "inputs.text == 'nope'"})
    # Skill output is optional so skipping the step doesn't fail validation.
    skill = SkillSpec(
        id="test.skill",
        version="1.0.0",
        name="Test",
        description="test",
        inputs={"text": FieldSpec(type="string", required=True)},
        outputs={"result": FieldSpec(type="string", required=False)},
        steps=(step,),
        metadata={},
    )
    executor = _CountingExecutor()
    engine = _build_engine(executor=executor, skill=skill)
    request = ExecutionRequest(
        skill_id="test.skill",
        inputs={"text": "hello"},
    )
    result = engine.execute(request)
    _test("engine: condition false → not executed", executor.call_count == 0)
    # The step result should be "skipped"
    sr = result.state.step_results.get("s1")
    _test(
        "engine: condition false → status skipped",
        sr is not None and sr.status == "skipped",
    )


def test_engine_retry():
    step = _make_step(
        config={
            "retry": {
                "max_attempts": 3,
                "backoff_seconds": 0.001,
                "backoff_multiplier": 1,
            },
        }
    )
    skill = _make_skill(steps=[step])
    executor = _CountingExecutor(fail_first_n=2)
    engine = _build_engine(executor=executor, skill=skill)
    request = ExecutionRequest(skill_id="test.skill", inputs={"text": "hello"})
    result = engine.execute(request)
    _test("engine: retry succeeds after failures", result.status == "completed")
    _test("engine: retry call count", executor.call_count == 3)


def test_engine_no_control_flow():
    """Plain step with no control flow config should work exactly as before."""
    step = _make_step()
    skill = _make_skill(steps=[step])
    executor = _CountingExecutor()
    engine = _build_engine(executor=executor, skill=skill)
    request = ExecutionRequest(skill_id="test.skill", inputs={"text": "hello"})
    result = engine.execute(request)
    _test("engine: no control flow → completed", result.status == "completed")
    _test("engine: no control flow → single call", executor.call_count == 1)


# ═══════════════════════════════════════════════════════════════
# 7. Router — step_control.resolve_router
# ═══════════════════════════════════════════════════════════════


def test_router_exact_match():
    s = _FakeState(vars={"doc_type": "invoice"})
    cfg = RouterConfig(
        on_expr="vars.doc_type",
        cases={"invoice": "doc.invoice.parse", "contract": "doc.contract.analyze"},
        default=None,
    )
    cap_id, meta = resolve_router(cfg, s)
    _test("router: exact match cap_id", cap_id == "doc.invoice.parse")
    _test("router: exact match meta", meta.get("router_matched") == "invoice")


def test_router_default():
    s = _FakeState(vars={"doc_type": "unknown"})
    cfg = RouterConfig(
        on_expr="vars.doc_type",
        cases={"invoice": "doc.invoice.parse"},
        default="doc.generic.process",
    )
    cap_id, meta = resolve_router(cfg, s)
    _test("router: default cap_id", cap_id == "doc.generic.process")
    _test("router: default meta", meta.get("router_matched") == "__default__")


def test_router_no_match_no_default():
    s = _FakeState(vars={"doc_type": "unknown"})
    cfg = RouterConfig(
        on_expr="vars.doc_type",
        cases={"invoice": "doc.invoice.parse"},
        default=None,
    )
    try:
        resolve_router(cfg, s)
        _test("router: no match raises", False)
    except Exception:
        _test("router: no match raises", True)


def test_router_from_config():
    cfg = RouterConfig.from_config(
        {
            "on": "vars.doc_type",
            "cases": {
                "invoice": "doc.invoice.parse",
                "contract": "doc.contract.analyze",
            },
            "default": "doc.generic.process",
        }
    )
    _test("router: from_config ok", cfg is not None)
    _test("router: from_config on", cfg.on_expr == "vars.doc_type")
    _test("router: from_config cases count", len(cfg.cases) == 2)
    _test("router: from_config default", cfg.default == "doc.generic.process")
    _test("router: from_config none", RouterConfig.from_config(None) is None)
    _test(
        "router: from_config missing on",
        RouterConfig.from_config({"cases": {"a": "b"}}) is None,
    )
    _test(
        "router: from_config missing cases",
        RouterConfig.from_config({"on": "x"}) is None,
    )


def test_router_with_condition():
    """Condition gates before router — if condition is false, step is skipped."""
    s = _FakeState(vars={"active": False, "doc_type": "invoice"})
    # Condition check first
    try:
        check_condition({"condition": "vars.active == true"}, s)
        _test("router+condition: skipped", False)
    except StepSkipped:
        _test("router+condition: skipped", True)


def test_engine_router():
    """Engine integration: router resolves to a different capability."""
    cap_a = _make_cap(
        "cap.alpha", outputs={"result": FieldSpec(type="string", required=True)}
    )
    cap_b = _make_cap(
        "cap.beta", outputs={"result": FieldSpec(type="string", required=True)}
    )
    # The step uses cap.alpha as default, but the router should pick cap.beta
    step = _make_step(
        uses="cap.alpha",
        config={
            "router": {
                "on": "inputs.text",
                "cases": {"hello": "cap.beta"},
                "default": "cap.alpha",
            },
        },
    )
    skill = _make_skill(steps=[step])
    executor = _CountingExecutor()
    cap_loader = _FakeCapLoader({"cap.alpha": cap_a, "cap.beta": cap_b})
    engine = ExecutionEngine(
        skill_loader=_FakeSkillLoader(skill),
        capability_loader=cap_loader,
        execution_planner=_FakePlanner(),
        reference_resolver=_FakeResolver(),
        capability_executor=executor,
        nested_skill_runner=_FakeNested(),
        audit_recorder=_FakeAudit(),
    )
    request = ExecutionRequest(skill_id="test.skill", inputs={"text": "hello"})
    result = engine.execute(request)
    _test("engine: router → completed", result.status == "completed")
    sr = result.state.step_results.get("s1")
    _test("engine: router meta present", sr is not None)


def test_engine_router_with_retry():
    """Router + retry: the routed capability is retried on failure."""
    cap_a = _make_cap("cap.alpha")
    cap_b = _make_cap("cap.beta")
    step = _make_step(
        uses="cap.alpha",
        config={
            "router": {
                "on": "inputs.text",
                "cases": {"hello": "cap.beta"},
                "default": "cap.alpha",
            },
            "retry": {
                "max_attempts": 3,
                "backoff_seconds": 0.001,
                "backoff_multiplier": 1,
            },
        },
    )
    skill = _make_skill(steps=[step])
    executor = _CountingExecutor(fail_first_n=2)
    cap_loader = _FakeCapLoader({"cap.alpha": cap_a, "cap.beta": cap_b})
    engine = ExecutionEngine(
        skill_loader=_FakeSkillLoader(skill),
        capability_loader=cap_loader,
        execution_planner=_FakePlanner(),
        reference_resolver=_FakeResolver(),
        capability_executor=executor,
        nested_skill_runner=_FakeNested(),
        audit_recorder=_FakeAudit(),
    )
    request = ExecutionRequest(skill_id="test.skill", inputs={"text": "hello"})
    result = engine.execute(request)
    _test("engine: router+retry → completed", result.status == "completed")
    _test("engine: router+retry call count", executor.call_count == 3)


# ═══════════════════════════════════════════════════════════════
# 8. Scatter-Gather — step_control.execute_scatter
# ═══════════════════════════════════════════════════════════════


def test_scatter_collect():
    cfg = ScatterConfig(capabilities=["cap.a", "cap.b", "cap.c"], merge="collect")

    def invoke(cap_id):
        return {"summary": f"result_{cap_id}"}, None

    produced, meta = execute_scatter(cfg, invoke, None)
    _test("scatter collect: 3 results", len(produced) == 3)
    _test(
        "scatter collect: cap.a present",
        produced.get("cap.a") == {"summary": "result_cap.a"},
    )
    _test(
        "scatter collect: cap.b present",
        produced.get("cap.b") == {"summary": "result_cap.b"},
    )
    _test("scatter collect: meta strategy", meta.get("scatter_strategy") == "collect")
    _test("scatter collect: meta count", meta.get("scatter_count") == 3)


def test_scatter_first_success():
    cfg = ScatterConfig(capabilities=["cap.slow", "cap.fast"], merge="first_success")

    def invoke(cap_id):
        if cap_id == "cap.slow":
            time.sleep(0.1)
            return {"val": "slow"}, None
        return {"val": "fast"}, None

    produced, meta = execute_scatter(cfg, invoke, None)
    _test("scatter first_success: got result", produced.get("val") is not None)
    _test(
        "scatter first_success: meta strategy",
        meta.get("scatter_strategy") == "first_success",
    )
    _test("scatter first_success: has winner", "scatter_winner" in meta)


def test_scatter_concat_lists():
    cfg = ScatterConfig(capabilities=["cap.a", "cap.b"], merge="concat_lists")

    def invoke(cap_id):
        if cap_id == "cap.a":
            return {"items": [1, 2]}, None
        return {"items": [3, 4]}, None

    produced, meta = execute_scatter(cfg, invoke, None)
    items = produced.get("items", [])
    _test("scatter concat: merged list", sorted(items) == [1, 2, 3, 4])
    _test("scatter concat: meta succeeded", meta.get("scatter_succeeded") == 2)


def test_scatter_partial_failure():
    cfg = ScatterConfig(capabilities=["cap.ok", "cap.fail"], merge="collect")

    def invoke(cap_id):
        if cap_id == "cap.fail":
            raise RuntimeError("boom")
        return {"val": "ok"}, None

    produced, meta = execute_scatter(cfg, invoke, None)
    _test("scatter partial: ok result present", "cap.ok" in produced)
    _test("scatter partial: fail absent", "cap.fail" not in produced)
    _test("scatter partial: meta failed count", meta.get("scatter_failed") == 1)
    _test("scatter partial: meta has errors", "scatter_errors" in meta)


def test_scatter_with_retry():
    cfg = ScatterConfig(capabilities=["cap.a", "cap.b"], merge="collect")
    retry = RetryPolicy(max_attempts=2, backoff_seconds=0.001, backoff_multiplier=1)
    call_counts: dict[str, int] = {}

    def invoke(cap_id):
        call_counts[cap_id] = call_counts.get(cap_id, 0) + 1
        if cap_id == "cap.a" and call_counts[cap_id] < 2:
            raise RuntimeError("transient")
        return {"val": cap_id}, None

    produced, meta = execute_scatter(cfg, invoke, retry)
    _test("scatter+retry: both succeeded", meta.get("scatter_succeeded") == 2)
    _test("scatter+retry: cap.a retried", call_counts.get("cap.a", 0) == 2)


def test_scatter_from_config():
    cfg = ScatterConfig.from_config(
        {
            "capabilities": ["cap.a", "cap.b", "cap.c"],
            "merge": "concat_lists",
        }
    )
    _test("scatter: from_config ok", cfg is not None)
    _test("scatter: from_config count", len(cfg.capabilities) == 3)
    _test("scatter: from_config merge", cfg.merge == "concat_lists")
    _test("scatter: from_config none", ScatterConfig.from_config(None) is None)
    _test(
        "scatter: from_config too few",
        ScatterConfig.from_config({"capabilities": ["a"]}) is None,
    )
    cfg2 = ScatterConfig.from_config({"capabilities": ["a", "b"]})
    _test(
        "scatter: from_config default merge",
        cfg2 is not None and cfg2.merge == "collect",
    )


def test_engine_scatter():
    """Engine integration: scatter with 2 capabilities in collect mode."""
    cap_a = _make_cap(
        "cap.alpha", outputs={"result": FieldSpec(type="string", required=True)}
    )
    cap_b = _make_cap(
        "cap.beta", outputs={"result": FieldSpec(type="string", required=True)}
    )
    step = StepSpec(
        id="s1",
        uses="cap.alpha",  # ignored when scatter is present
        input_mapping={"text": "inputs.text"},
        output_mapping={},  # no output mapping — scatter produces dict-of-dicts
        config={
            "scatter": {
                "capabilities": ["cap.alpha", "cap.beta"],
                "merge": "collect",
            },
        },
    )
    skill = SkillSpec(
        id="test.skill",
        version="1.0.0",
        name="Test",
        description="test",
        inputs={"text": FieldSpec(type="string", required=True)},
        outputs={"result": FieldSpec(type="string", required=False)},
        steps=(step,),
        metadata={},
    )
    executor = _CountingExecutor()
    cap_loader = _FakeCapLoader({"cap.alpha": cap_a, "cap.beta": cap_b})
    engine = ExecutionEngine(
        skill_loader=_FakeSkillLoader(skill),
        capability_loader=cap_loader,
        execution_planner=_FakePlanner(),
        reference_resolver=_FakeResolver(),
        capability_executor=executor,
        nested_skill_runner=_FakeNested(),
        audit_recorder=_FakeAudit(),
    )
    request = ExecutionRequest(skill_id="test.skill", inputs={"text": "hello"})
    result = engine.execute(request)
    _test("engine: scatter → completed", result.status == "completed")
    _test("engine: scatter call count >= 2", executor.call_count >= 2)


# ═══════════════════════════════════════════════════════════════
# Runner
# ═══════════════════════════════════════════════════════════════


def main():
    global _pass, _fail

    # Expression evaluator
    test_expression_literals()
    test_expression_refs()
    test_expression_nested_refs()
    test_expression_comparisons()
    test_expression_boolean()
    test_expression_in_operator()
    test_expression_parentheses()
    test_expression_errors()

    # Condition gate
    test_condition_no_config()
    test_condition_true()
    test_condition_false()

    # Retry
    test_retry_no_policy()
    test_retry_success_first_attempt()
    test_retry_success_after_failures()
    test_retry_exhaustion()
    test_retry_from_config()

    # Foreach
    test_foreach_basic()
    test_foreach_empty_list()
    test_foreach_with_retry()
    test_foreach_non_list_raises()
    test_foreach_from_config()

    # While
    test_while_basic()
    test_while_max_iterations()
    test_while_with_retry()
    test_while_from_config()

    # Engine integration (original)
    test_engine_condition_true()
    test_engine_condition_false()
    test_engine_retry()
    test_engine_no_control_flow()

    # Router
    test_router_exact_match()
    test_router_default()
    test_router_no_match_no_default()
    test_router_from_config()
    test_router_with_condition()
    test_engine_router()
    test_engine_router_with_retry()

    # Scatter-Gather
    test_scatter_collect()
    test_scatter_first_success()
    test_scatter_concat_lists()
    test_scatter_partial_failure()
    test_scatter_with_retry()
    test_scatter_from_config()
    test_engine_scatter()

    print(f"\n  step_control_flow: {_pass} passed, {_fail} failed")
    if _fail:
        sys.exit(1)


if __name__ == "__main__":
    main()

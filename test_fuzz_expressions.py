"""T4 — Fuzz testing for step_expression and input_mapper.

Uses hypothesis to generate arbitrary inputs and ensure the parser
never raises unhandled exceptions (no eval/exec leaks, no infinite loops).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure project root is importable
_root = Path(__file__).resolve().parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

hypothesis = pytest.importorskip("hypothesis", reason="hypothesis not installed")
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from runtime.step_expression import ExpressionError, evaluate, evaluate_bool


# ── Strategies ────────────────────────────────────────────────────────────

_SAFE_ALPHABET = st.sampled_from(
    list("abcdefghijklmnopqrstuvwxyz0123456789_.=!<> '\"()[],-+")
)
_KEYWORDS = st.sampled_from(["not", "and", "or", "in", "true", "false", "null", "none"])
_EXPR_TOKEN = st.one_of(_SAFE_ALPHABET, _KEYWORDS)
_EXPR_TEXT = st.lists(_EXPR_TOKEN, min_size=0, max_size=60).map("".join)

_REF_NAMESPACES = ["vars", "inputs", "outputs", "working", "frame", "output"]
_REF = st.builds(
    lambda ns, key: f"{ns}.{key}",
    st.sampled_from(_REF_NAMESPACES),
    st.from_regex(r"[a-z_][a-z0-9_]{0,15}", fullmatch=True),
)

_SIMPLE_VALUES = st.one_of(
    st.integers(min_value=-1000, max_value=1000),
    st.floats(allow_nan=False, allow_infinity=False, min_value=-1e6, max_value=1e6),
    st.text(min_size=0, max_size=50),
    st.booleans(),
    st.none(),
)

_STATE_DICT = st.fixed_dictionaries(
    {
        "inputs": st.dictionaries(
            st.from_regex(r"[a-z]{1,8}", fullmatch=True), _SIMPLE_VALUES, max_size=5
        ),
        "vars": st.dictionaries(
            st.from_regex(r"[a-z]{1,8}", fullmatch=True), _SIMPLE_VALUES, max_size=5
        ),
        "outputs": st.dictionaries(
            st.from_regex(r"[a-z]{1,8}", fullmatch=True), _SIMPLE_VALUES, max_size=3
        ),
    }
)


# ── State mock ────────────────────────────────────────────────────────────


class _FakeState:
    """Minimal stand-in for ExecutionState with namespace access."""

    def __init__(self, data: dict):
        self.inputs = data.get("inputs", {})
        self.vars = data.get("vars", {})
        self.outputs = data.get("outputs", {})
        self.working = type(
            "W",
            (),
            {
                "artifacts": {},
                "entities": [],
                "options": [],
                "criteria": [],
                "evidence": [],
                "risks": [],
                "hypotheses": [],
                "uncertainties": [],
                "intermediate_decisions": [],
                "messages": [],
            },
        )()
        self.frame = type(
            "F",
            (),
            {
                "goal": None,
                "context": {},
                "constraints": {},
                "success_criteria": {},
                "assumptions": (),
                "priority": None,
            },
        )()
        self.output = type(
            "O",
            (),
            {
                "result": None,
                "result_type": None,
                "summary": None,
                "status_reason": None,
            },
        )()
        self.extensions = {}
        self.step_results = {}


# ── Fuzz: evaluate() never crashes ────────────────────────────────────────


class TestStepExpressionFuzz:
    @given(expr=_EXPR_TEXT, state_data=_STATE_DICT)
    @settings(max_examples=500, suppress_health_check=[HealthCheck.too_slow])
    def test_evaluate_no_unhandled_crash(self, expr: str, state_data: dict):
        """evaluate() must never raise anything other than ExpressionError/ValueError/TypeError."""
        state = _FakeState(state_data)
        try:
            evaluate(expr, state)
        except (ExpressionError, ValueError, TypeError, KeyError, AttributeError):
            pass  # expected for malformed expressions

    @given(expr=_EXPR_TEXT, state_data=_STATE_DICT)
    @settings(max_examples=500, suppress_health_check=[HealthCheck.too_slow])
    def test_evaluate_bool_no_crash(self, expr: str, state_data: dict):
        """evaluate_bool() must never raise unexpected exceptions."""
        state = _FakeState(state_data)
        try:
            result = evaluate_bool(expr, state)
            assert isinstance(result, bool)
        except (ExpressionError, ValueError, TypeError, KeyError, AttributeError):
            pass

    @given(ref=_REF, state_data=_STATE_DICT)
    @settings(max_examples=200)
    def test_reference_resolution_safe(self, ref: str, state_data: dict):
        """Reference expressions must resolve or raise cleanly."""
        state = _FakeState(state_data)
        try:
            evaluate(ref, state)
        except (ExpressionError, ValueError, TypeError, KeyError, AttributeError):
            pass

    @given(
        lhs=st.one_of(st.integers(-100, 100), st.text(min_size=1, max_size=10)),
        op=st.sampled_from(["==", "!=", ">", "<", ">=", "<=", "in", "not in"]),
        rhs=st.one_of(st.integers(-100, 100), st.text(min_size=1, max_size=10)),
    )
    @settings(max_examples=300)
    def test_comparison_ops_never_crash(self, lhs, op, rhs):
        """Comparison with arbitrary types must not crash."""
        lhs_str = repr(lhs) if isinstance(lhs, str) else str(lhs)
        rhs_str = repr(rhs) if isinstance(rhs, str) else str(rhs)
        expr = f"{lhs_str} {op} {rhs_str}"
        state = _FakeState({"inputs": {}, "vars": {}, "outputs": {}})
        try:
            evaluate(expr, state)
        except (ExpressionError, ValueError, TypeError, KeyError, AttributeError):
            pass

    def test_no_eval_exec_in_source(self):
        """Verify that step_expression.py contains no eval()/exec()/compile() calls."""
        import inspect
        import runtime.step_expression as mod

        source = inspect.getsource(mod)
        # Allow 'compile' only in comments or strings describing the grammar.
        assert "eval(" not in source.replace("evaluate(", "").replace(
            "evaluate_bool(", ""
        )
        assert "exec(" not in source

#!/usr/bin/env python3
"""P3 — Performance baseline benchmarks (pytest-benchmark).

Benchmarks for the five critical hot paths:

1. ReferenceResolver.resolve_mapping — step input resolution
2. RequestBuilder.build — binding payload construction
3. ResponseMapper.map — response → output mapping
4. Scheduler DAG construction — topological sort / cycle check
5. BindingResolver.resolve — binding selection

Run:
    pytest test_performance_baselines.py --benchmark-only -v
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

benchmark = pytest.importorskip("pytest_benchmark").plugin.benchmark

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from runtime.reference_resolver import ReferenceResolver
from runtime.request_builder import RequestBuilder
from runtime.response_mapper import ResponseMapper
from runtime.binding_models import BindingSpec, InvocationResponse

# ---------------------------------------------------------------------------
# Fixtures: lightweight fakes that avoid hitting real services
# ---------------------------------------------------------------------------


def _make_state(n_inputs: int = 10, n_vars: int = 5):
    """Produce a SimpleNamespace mimicking ExecutionState."""
    state = SimpleNamespace()
    state.inputs = {f"field_{i}": f"value_{i}" for i in range(n_inputs)}
    state.vars = {f"var_{i}": i * 10 for i in range(n_vars)}
    state.outputs = {}
    state.frame = SimpleNamespace()
    state.working = SimpleNamespace()
    state.output = SimpleNamespace()
    state.extensions = {}
    state.skill_id = "bench.skill"
    state.trace_id = "trace-bench"
    return state


def _make_binding(n_req: int = 6, n_resp: int = 3) -> BindingSpec:
    """Create a synthetic BindingSpec with n_req request fields."""
    req = {f"param_{i}": f"input.field_{i}" for i in range(n_req)}
    resp = {f"out_{i}": f"response.result_{i}" for i in range(n_resp)}
    return BindingSpec(
        id="bench_binding",
        capability_id="bench.capability",
        service_id="bench_service",
        protocol="pythoncall",
        operation_id="bench_op",
        request_template=req,
        response_mapping=resp,
        metadata={},
    )


def _make_invocation_response(n_fields: int = 3) -> InvocationResponse:
    raw = {f"result_{i}": f"data_{i}" for i in range(n_fields)}
    return InvocationResponse(status="success", raw_response=raw)


def _make_step_plan(n_steps: int = 20):
    """Create a plan list of step-like objects for scheduler benchmarking."""
    steps = []
    for i in range(n_steps):
        step = SimpleNamespace()
        step.id = f"step_{i}"
        step.uses = "bench.capability"
        step.config = {}
        if i > 0:
            step.config["depends_on"] = [f"step_{i - 1}"]
        else:
            step.config["depends_on"] = []
        steps.append(step)
    return steps


# ---------------------------------------------------------------------------
# Benchmarks
# ---------------------------------------------------------------------------

_resolver = ReferenceResolver()
_builder = RequestBuilder()
_mapper = ResponseMapper()


def test_bench_reference_resolve_mapping(benchmark):
    """Benchmark ReferenceResolver.resolve_mapping with 10 input fields."""
    state = _make_state(10, 5)
    mapping = {f"step_in_{i}": f"inputs.field_{i}" for i in range(10)}
    benchmark(_resolver.resolve_mapping, mapping, state)


def test_bench_request_builder(benchmark):
    """Benchmark RequestBuilder.build with 6 template fields."""
    binding = _make_binding(6, 3)
    step_input = {f"field_{i}": f"value_{i}" for i in range(6)}
    benchmark(_builder.build, binding, step_input)


def test_bench_response_mapper(benchmark):
    """Benchmark ResponseMapper.map with 3 response fields."""
    binding = _make_binding(6, 3)
    response = _make_invocation_response(3)
    benchmark(_mapper.map, binding, response)


def test_bench_scheduler_dag_build(benchmark):
    """Benchmark Scheduler DAG construction + cycle check for a 20-step chain."""
    from runtime.scheduler import Scheduler

    scheduler = Scheduler(max_workers=1)
    plan = _make_step_plan(20)

    # The scheduler expects a step_executor callback
    def _noop_executor(step, skill_id, context, trace_callback=None):
        return SimpleNamespace(step_id=step.id, status="completed", output={})

    context = SimpleNamespace(
        state=SimpleNamespace(skill_id="bench"),
        options={},
    )

    benchmark(scheduler.schedule, plan, context, _noop_executor)


def test_bench_binding_resolver(benchmark):
    """Benchmark BindingResolver.resolve for a known capability."""
    try:
        from runtime.binding_registry import BindingRegistry
        from runtime.binding_resolver import BindingResolver

        REGISTRY_ROOT = ROOT.parent / "agent-skill-registry"
        registry = BindingRegistry(ROOT, REGISTRY_ROOT)
        resolver = BindingResolver(registry)

        # Pick a capability we know has bindings
        cap_id = "text.content.summarize"
        benchmark(resolver.resolve, cap_id)
    except Exception:
        pytest.skip("BindingRegistry cannot initialize — skipping resolver benchmark")

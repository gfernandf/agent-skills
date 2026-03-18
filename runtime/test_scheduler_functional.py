import time
import threading
from runtime.scheduler import Scheduler
from runtime.models import StepSpec, StepResult, ExecutionContext, ExecutionOptions, ExecutionState

def make_step(step_id, depends_on=None, sleep=0):
    return StepSpec(
        id=step_id,
        uses=f"mock.{step_id}",
        input_mapping={},
        output_mapping={},
        config={"depends_on": depends_on or [], "sleep": sleep},
    )

def mock_step_executor(step, skill_id, context, trace_callback):
    sleep = step.config.get("sleep", 0)
    if sleep:
        time.sleep(sleep)
    # Simula fallo si step_id contiene 'fail'
    status = "failed" if "fail" in step.id else "completed"
    return StepResult(
        step_id=step.id,
        uses=step.uses,
        status=status,
        resolved_input={},
        produced_output={"out": step.id},
        started_at=None,
        finished_at=None,
        error_message=("fail" if status == "failed" else None),
    )

def test_parallel_and_dependencies():
    # A y B no dependen de nadie, C depende de A y B
    steps = [
        make_step("A", sleep=1),
        make_step("B", sleep=1),
        make_step("C", depends_on=["A", "B"]),
    ]
    context = ExecutionContext(
        state=ExecutionState(skill_id="test", inputs={}, vars={}, outputs={}, step_results={}, written_targets=set(), events=[]),
        options=ExecutionOptions(fail_fast=True),
    )
    scheduler = Scheduler(max_workers=2)
    t0 = time.time()
    results = scheduler.schedule(steps, context, mock_step_executor)
    t1 = time.time()
    # C debe ejecutarse después de A y B, pero A y B en paralelo
    assert set(r.step_id for r in results) == {"A", "B", "C"}
    assert t1 - t0 < 2.2  # Debe ser ~2s, no ~3s
    print("test_parallel_and_dependencies PASSED")

def test_fail_fast():
    # A y B en paralelo, B falla, C depende de ambos
    steps = [
        make_step("A", sleep=1),
        make_step("B_fail", sleep=1),
        make_step("C", depends_on=["A", "B_fail"]),
    ]
    context = ExecutionContext(
        state=ExecutionState(skill_id="test", inputs={}, vars={}, outputs={}, step_results={}, written_targets=set(), events=[]),
        options=ExecutionOptions(fail_fast=True),
    )
    scheduler = Scheduler(max_workers=2)
    results = scheduler.schedule(steps, context, mock_step_executor)
    # Debe abortar tras el fallo de B_fail
    assert any(r.status == "failed" for r in results)
    assert not any(r.step_id == "C" for r in results)
    print("test_fail_fast PASSED")

def test_sequential_fallback():
    # Forzar modo secuencial
    steps = [make_step("A"), make_step("B", depends_on=["A"]), make_step("C", depends_on=["B"])]
    context = ExecutionContext(
        state=ExecutionState(skill_id="test", inputs={}, vars={}, outputs={}, step_results={}, written_targets=set(), events=[]),
        options=ExecutionOptions(fail_fast=True),
    )
    scheduler = Scheduler(max_workers=1)
    results = scheduler.schedule(steps, context, mock_step_executor)
    assert [r.step_id for r in results] == ["A", "B", "C"]
    print("test_sequential_fallback PASSED")

def test_implicit_sequential_no_depends_on():
    """Steps without depends_on must run sequentially (v1 backward compat)."""
    execution_order = []

    def tracking_executor(step, skill_id, context, trace_callback):
        execution_order.append(step.id)
        time.sleep(0.05)
        return StepResult(
            step_id=step.id, uses=step.uses, status="completed",
            resolved_input={}, produced_output={},
            started_at=None, finished_at=None,
        )

    # Steps with NO depends_on key in config at all
    steps = [
        StepSpec(id="X", uses="mock.X", input_mapping={}, output_mapping={}, config={}),
        StepSpec(id="Y", uses="mock.Y", input_mapping={}, output_mapping={}, config={}),
        StepSpec(id="Z", uses="mock.Z", input_mapping={}, output_mapping={}, config={}),
    ]
    context = ExecutionContext(
        state=ExecutionState(skill_id="test", inputs={}, vars={}, outputs={},
                             step_results={}, written_targets=set(), events=[]),
        options=ExecutionOptions(fail_fast=True),
    )
    scheduler = Scheduler(max_workers=4)
    results = scheduler.schedule(steps, context, tracking_executor)
    assert [r.step_id for r in results] == ["X", "Y", "Z"], f"Got: {[r.step_id for r in results]}"
    assert execution_order == ["X", "Y", "Z"], f"Execution order was: {execution_order}"
    print("test_implicit_sequential_no_depends_on PASSED")


def test_explicit_empty_enables_parallelism():
    """Steps with depends_on=[] explicitly opt into parallelism."""
    steps = [
        make_step("P", depends_on=[], sleep=0.5),
        make_step("Q", depends_on=[], sleep=0.5),
    ]
    context = ExecutionContext(
        state=ExecutionState(skill_id="test", inputs={}, vars={}, outputs={},
                             step_results={}, written_targets=set(), events=[]),
        options=ExecutionOptions(fail_fast=True),
    )
    scheduler = Scheduler(max_workers=2)
    t0 = time.time()
    results = scheduler.schedule(steps, context, mock_step_executor)
    elapsed = time.time() - t0
    assert len(results) == 2
    assert elapsed < 1.0, f"Should be parallel (~0.5s) but took {elapsed:.2f}s"
    print("test_explicit_empty_enables_parallelism PASSED")


if __name__ == "__main__":
    test_parallel_and_dependencies()
    test_fail_fast()
    test_sequential_fallback()
    test_implicit_sequential_no_depends_on()
    test_explicit_empty_enables_parallelism()
    print("All Scheduler functional tests PASSED.")

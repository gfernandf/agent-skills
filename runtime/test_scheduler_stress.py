import time
import random
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
    # Simula fallo aleatorio
    if random.random() < 0.01:
        return StepResult(
            step_id=step.id,
            uses=step.uses,
            status="failed",
            resolved_input={},
            produced_output=None,
            error_message="random fail",
        )
    return StepResult(
        step_id=step.id,
        uses=step.uses,
        status="completed",
        resolved_input={},
        produced_output={"out": step.id},
    )

def stress_test_scheduler(num_steps=200, max_parallel=16, max_deps=5):
    # Genera un grafo aleatorio de dependencias
    steps = []
    for i in range(num_steps):
        step_id = f"S{i}"
        if i == 0:
            deps = []
        else:
            deps = random.sample([f"S{j}" for j in range(i)], k=random.randint(0, min(max_deps, i)))
        steps.append(make_step(step_id, depends_on=deps, sleep=random.uniform(0, 0.01)))
    context = ExecutionContext(
        state=ExecutionState(skill_id="stress", inputs={}, vars={}, outputs={}, step_results={}, written_targets=set(), events=[]),
        options=ExecutionOptions(fail_fast=False),
    )
    scheduler = Scheduler(max_workers=max_parallel)
    t0 = time.time()
    results = scheduler.schedule(steps, context, mock_step_executor)
    t1 = time.time()
    completed = sum(1 for r in results if r.status == "completed")
    failed = sum(1 for r in results if r.status == "failed")
    skipped = sum(1 for r in results if r.status == "skipped")
    print(f"STRESS TEST: {num_steps} steps, {max_parallel} parallel, completed={completed}, failed={failed}, skipped={skipped}, time={t1-t0:.2f}s")
    assert completed + failed + skipped == num_steps
    assert t1 - t0 < 10, "Stress test took too long!"
    print("stress_test_scheduler PASSED")

if __name__ == "__main__":
    for _ in range(5):
        stress_test_scheduler(num_steps=300, max_parallel=32, max_deps=10)
    print("All stress tests PASSED.")

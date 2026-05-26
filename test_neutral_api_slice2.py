from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

from customer_facing.neutral_api import NeutralRuntimeAPI
from runtime.checkpoint_manager import CheckpointManager, InMemoryCheckpointStoreBackend
from runtime.execution_state import create_execution_state, mark_finished, mark_started
from runtime.run_store import RunStoreV2


def _build_api_without_init() -> NeutralRuntimeAPI:
    # We only exercise state-management methods that do not require full runtime wiring.
    return NeutralRuntimeAPI.__new__(NeutralRuntimeAPI)


def test_legacy_projection_maps_canceled_to_failed() -> None:
    api = _build_api_without_init()
    store = RunStoreV2(max_runs=10)

    store.create_run_record(
        run_id="r-legacy",
        skill_id="x.y",
        trace_id="t-1",
        status="running",
    )
    canceled = api.cancel_run("r-legacy", run_store=store)
    legacy_view = api.get_run("r-legacy", run_store=store, legacy_projection=True)

    assert canceled["ok"] is True
    assert canceled["data"]["status"] == "canceled"
    assert legacy_view["ok"] is True
    assert legacy_view["data"]["status"] == "failed"


def test_list_checkpoints_and_resume_state_only() -> None:
    api = _build_api_without_init()
    store = RunStoreV2(max_runs=10)
    checkpoints = CheckpointManager(InMemoryCheckpointStoreBackend())

    store.create_run_record(
        run_id="r-check",
        skill_id="x.y",
        trace_id="t-2",
        status="waiting_for_human",
    )
    state = create_execution_state("x.y", {"a": 1}, trace_id="t-2")
    mark_started(state)
    record = checkpoints.save_checkpoint(
        run_id="r-check",
        state=state,
        step_id="s-1",
        kind="run_started",
    )
    store.patch_run("r-check", {"checkpoint_head": record.checkpoint_id})

    listed = api.list_checkpoints(
        "r-check",
        run_store=store,
        checkpoint_manager=checkpoints,
    )
    resumed = api.resume_run(
        "r-check",
        run_store=store,
        checkpoint_manager=checkpoints,
    )

    assert listed["ok"] is True
    assert listed["data"]["total"] == 1
    assert listed["data"]["checkpoint_head"] == record.checkpoint_id
    assert resumed["ok"] is True
    assert resumed["data"]["resume"]["mode"] == "state_only"
    assert store.get_run("r-check")["status"] == "running"


def test_execute_skill_async_updates_checkpoint_head() -> None:
    api = _build_api_without_init()
    store = RunStoreV2(max_runs=10)
    checkpoints = CheckpointManager(InMemoryCheckpointStoreBackend())

    def _fake_execute(*, skill_id, inputs, trace_id, **_kwargs):
        state = create_execution_state(skill_id, inputs or {}, trace_id=trace_id)
        mark_started(state)
        state.current_step = "s-finish"
        mark_finished(state, "completed")
        return SimpleNamespace(state=state), {
            "skill_id": skill_id,
            "status": "completed",
            "outputs": {"ok": True},
            "trace_id": trace_id,
        }

    api._execute_skill_with_result = _fake_execute  # type: ignore[attr-defined]

    with ThreadPoolExecutor(max_workers=1) as pool:
        launch = api.execute_skill_async(
            skill_id="x.y",
            inputs={"n": 1},
            trace_id="t-3",
            run_store=store,
            checkpoint_manager=checkpoints,
            async_pool=pool,
        )

        run_id = launch["run_id"]
        deadline = time.time() + 2.0
        while time.time() < deadline:
            run = store.get_run(run_id)
            if isinstance(run, dict) and run.get("status") == "completed":
                break
            time.sleep(0.05)

    run = store.get_run(run_id)
    assert isinstance(run, dict)
    assert run.get("status") == "completed"
    assert isinstance(run.get("checkpoint_head"), str)
    assert run["checkpoint_head"]

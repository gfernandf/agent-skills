from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

from customer_facing.neutral_api import NeutralRuntimeAPI
from runtime.checkpoint_manager import CheckpointManager, InMemoryCheckpointStoreBackend
from runtime.errors import SafetyConfirmationRequiredError
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
    def _fake_execute(*, skill_id, inputs, trace_id, initial_state=None, **_kwargs):
        assert initial_state is not None
        initial_state.outputs["ok"] = True
        mark_finished(initial_state, "completed")
        return SimpleNamespace(state=initial_state), {
            "skill_id": skill_id,
            "status": "completed",
            "outputs": {"ok": True},
            "trace_id": trace_id,
        }

    api._execute_skill_with_result = _fake_execute  # type: ignore[attr-defined]

    with ThreadPoolExecutor(max_workers=1) as pool:
        resumed = api.resume_run(
            "r-check",
            run_store=store,
            checkpoint_manager=checkpoints,
            async_pool=pool,
        )

        deadline = time.time() + 2.0
        while time.time() < deadline:
            run = store.get_run("r-check")
            if isinstance(run, dict) and run.get("status") == "completed":
                break
            time.sleep(0.05)

    assert listed["ok"] is True
    assert listed["data"]["total"] == 1
    assert listed["data"]["checkpoint_head"] == record.checkpoint_id
    assert resumed["ok"] is True
    assert resumed["data"]["resume"]["mode"] == "checkpoint_resume"
    assert store.get_run("r-check")["status"] == "completed"


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


def test_resume_run_executes_from_checkpoint() -> None:
    api = _build_api_without_init()
    store = RunStoreV2(max_runs=10)
    checkpoints = CheckpointManager(InMemoryCheckpointStoreBackend())

    state = create_execution_state("x.y", {"n": 1}, trace_id="t-4")
    mark_started(state)
    state.vars["mid"] = "cached"

    store.create_run_record(
        run_id="r-resume",
        skill_id="x.y",
        trace_id="t-4",
        status="waiting_for_human",
        metadata={"inputs": {"n": 1}, "execution_channel": "http-async"},
    )
    record = checkpoints.save_checkpoint(
        run_id="r-resume",
        state=state,
        step_id="s-1",
        kind="run_waiting",
    )
    store.patch_run("r-resume", {"checkpoint_head": record.checkpoint_id})

    def _fake_execute(*, skill_id, inputs, trace_id, initial_state=None, **_kwargs):
        assert initial_state is not None
        assert initial_state.vars.get("mid") == "cached"
        initial_state.outputs["ok"] = True
        mark_finished(initial_state, "completed")
        return SimpleNamespace(state=initial_state), {
            "skill_id": skill_id,
            "status": "completed",
            "outputs": {"ok": True},
            "trace_id": trace_id,
        }

    api._execute_skill_with_result = _fake_execute  # type: ignore[attr-defined]

    with ThreadPoolExecutor(max_workers=1) as pool:
        response = api.resume_run(
            "r-resume",
            run_store=store,
            checkpoint_manager=checkpoints,
            async_pool=pool,
        )
        assert response["ok"] is True
        assert response["data"]["resume"]["mode"] == "checkpoint_resume"

        deadline = time.time() + 2.0
        while time.time() < deadline:
            run = store.get_run("r-resume")
            if isinstance(run, dict) and run.get("status") == "completed":
                break
            time.sleep(0.05)

    run = store.get_run("r-resume")
    assert isinstance(run, dict)
    assert run.get("status") == "completed"
    assert run.get("resume_from_checkpoint_id") == record.checkpoint_id
    assert isinstance(run.get("checkpoint_head"), str)


def test_async_approval_flow_runs_after_waiting() -> None:
    api = _build_api_without_init()
    store = RunStoreV2(max_runs=10)
    checkpoints = CheckpointManager(InMemoryCheckpointStoreBackend())

    waiting_state = create_execution_state("x.y", {"n": 1}, trace_id="t-5")
    mark_started(waiting_state)

    def _fake_execute(*, skill_id, inputs, trace_id, confirmed_capabilities=None, initial_state=None, **_kwargs):
        if initial_state is None:
            error = SafetyConfirmationRequiredError(
                "confirmation needed",
                skill_id=skill_id,
                step_id="step-1",
                capability_id="cap.confirm",
            )
            error.execution_state = waiting_state  # type: ignore[attr-defined]
            raise error
        assert "cap.confirm" in set(confirmed_capabilities or [])
        initial_state.outputs["ok"] = True
        mark_finished(initial_state, "completed")
        return SimpleNamespace(state=initial_state), {
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
            trace_id="t-5",
            run_store=store,
            checkpoint_manager=checkpoints,
            async_pool=pool,
        )
        assert launch["status"] == "running"

        deadline = time.time() + 2.0
        while time.time() < deadline:
            run = store.get_run(launch["run_id"])
            if isinstance(run, dict) and run.get("status") == "waiting_for_human":
                break
            time.sleep(0.05)

        run = store.get_run(launch["run_id"])
        assert isinstance(run, dict)
        assert run.get("status") == "waiting_for_human"

        approval = api.approve_run(
            launch["run_id"],
            approver="lead-1",
            notes="approved",
            run_store=store,
            checkpoint_manager=checkpoints,
            async_pool=pool,
        )
        assert approval["ok"] is True
        assert approval["data"]["resume"]["mode"] == "checkpoint_resume"

        deadline = time.time() + 2.0
        while time.time() < deadline:
            run = store.get_run(launch["run_id"])
            if isinstance(run, dict) and run.get("status") == "completed":
                break
            time.sleep(0.05)

    run = store.get_run(launch["run_id"])
    assert isinstance(run, dict)
    assert run.get("status") == "completed"
    assert run.get("error") is None


def test_deny_run_cancels_waiting_run() -> None:
    api = _build_api_without_init()
    store = RunStoreV2(max_runs=10)

    store.create_run_record(
        run_id="r-deny",
        skill_id="x.y",
        trace_id="t-6",
        status="waiting_for_human",
        metadata={"inputs": {"n": 1}},
    )

    denied = api.deny_run(
        "r-deny",
        approver="lead-2",
        notes="not now",
        run_store=store,
        legacy_projection=False,
    )

    assert denied["ok"] is True
    assert denied["data"]["status"] == "canceled"
    assert denied["data"]["approval_request"]["status"] == "denied"
    assert store.get_run("r-deny")["status"] == "canceled"


def test_replay_run_executes_from_checkpoint() -> None:
    api = _build_api_without_init()
    store = RunStoreV2(max_runs=10)
    checkpoints = CheckpointManager(InMemoryCheckpointStoreBackend())

    source_state = create_execution_state("x.y", {"n": 1}, trace_id="t-7")
    mark_started(source_state)
    source_state.vars["mid"] = "cached"
    record = checkpoints.save_checkpoint(
        run_id="r-source",
        state=source_state,
        step_id="s-1",
        kind="run_finished",
    )
    store.create_run_record(
        run_id="r-source",
        skill_id="x.y",
        trace_id="t-7",
        status="completed",
        checkpoint_head=record.checkpoint_id,
        metadata={"inputs": {"n": 1}, "execution_channel": "http-async"},
    )

    def _fake_execute(*, skill_id, inputs, trace_id, initial_state=None, **_kwargs):
        assert initial_state is not None
        assert initial_state.vars.get("mid") == "cached"
        initial_state.outputs["ok"] = True
        mark_finished(initial_state, "completed")
        return SimpleNamespace(state=initial_state), {
            "skill_id": skill_id,
            "status": "completed",
            "outputs": {"ok": True},
            "trace_id": trace_id,
        }

    api._execute_skill_with_result = _fake_execute  # type: ignore[attr-defined]

    with ThreadPoolExecutor(max_workers=1) as pool:
        response = api.replay_run(
            "r-source",
            run_store=store,
            checkpoint_manager=checkpoints,
            async_pool=pool,
        )
        assert response["ok"] is True
        assert response["data"]["replay"]["mode"] == "checkpoint_replay"

        replay_id = response["data"]["run"]["run_id"]
        deadline = time.time() + 2.0
        while time.time() < deadline:
            run = store.get_run(replay_id)
            if isinstance(run, dict) and run.get("status") == "completed":
                break
            time.sleep(0.05)

    run = store.get_run(replay_id)
    assert isinstance(run, dict)
    assert run.get("status") == "completed"
    assert run.get("metadata", {}).get("source_run_id") == "r-source"

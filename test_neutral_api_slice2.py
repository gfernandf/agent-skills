from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

from customer_facing.neutral_api import NeutralRuntimeAPI
from runtime.checkpoint_manager import CheckpointManager, InMemoryCheckpointStoreBackend
from runtime.errors import SafetyConfirmationRequiredError
from runtime.execution_state import create_execution_state, mark_finished, mark_started
from runtime.metrics import METRICS
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


def test_execute_skill_async_idempotency_key_reuses_run() -> None:
    api = _build_api_without_init()
    store = RunStoreV2(max_runs=10)
    checkpoints = CheckpointManager(InMemoryCheckpointStoreBackend())

    def _fake_execute(*, skill_id, inputs, trace_id, **_kwargs):
        state = create_execution_state(skill_id, inputs or {}, trace_id=trace_id)
        mark_started(state)
        time.sleep(0.1)
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
        first = api.execute_skill_async(
            skill_id="x.y",
            inputs={"n": 2},
            trace_id="t-idem",
            idempotency_key="idem-123",
            run_store=store,
            checkpoint_manager=checkpoints,
            async_pool=pool,
        )
        second = api.execute_skill_async(
            skill_id="x.y",
            inputs={"n": 2},
            trace_id="t-idem",
            idempotency_key="idem-123",
            run_store=store,
            checkpoint_manager=checkpoints,
            async_pool=pool,
        )

        deadline = time.time() + 2.0
        while time.time() < deadline:
            run = store.get_run(first["run_id"])
            if isinstance(run, dict) and run.get("status") == "completed":
                break
            time.sleep(0.05)

    assert first["run_id"] == second["run_id"]
    assert second.get("idempotent_replay") is True
    runs = store.list_runs_page(limit=10)
    assert len(runs) == 1


def test_execute_skill_async_idempotency_key_conflicts_on_payload_change() -> None:
    api = _build_api_without_init()
    store = RunStoreV2(max_runs=10)
    checkpoints = CheckpointManager(InMemoryCheckpointStoreBackend())

    def _fake_execute(*, skill_id, inputs, trace_id, **_kwargs):
        state = create_execution_state(skill_id, inputs or {}, trace_id=trace_id)
        mark_started(state)
        time.sleep(0.1)
        mark_finished(state, "completed")
        return SimpleNamespace(state=state), {
            "skill_id": skill_id,
            "status": "completed",
            "outputs": {"ok": True},
            "trace_id": trace_id,
        }

    api._execute_skill_with_result = _fake_execute  # type: ignore[attr-defined]

    with ThreadPoolExecutor(max_workers=1) as pool:
        first = api.execute_skill_async(
            skill_id="x.y",
            inputs={"n": 2},
            trace_id="t-idem-conflict",
            idempotency_key="idem-456",
            run_store=store,
            checkpoint_manager=checkpoints,
            async_pool=pool,
        )

        second = api.execute_skill_async(
            skill_id="x.y",
            inputs={"n": 3},
            trace_id="t-idem-conflict",
            idempotency_key="idem-456",
            run_store=store,
            checkpoint_manager=checkpoints,
            async_pool=pool,
        )

        deadline = time.time() + 2.0
        while time.time() < deadline:
            run = store.get_run(first["run_id"])
            if isinstance(run, dict) and run.get("status") == "completed":
                break
            time.sleep(0.05)

    assert second["error"]["code"] == "idempotency_conflict"
    assert second["error"]["status"] == 409


def test_execute_skill_async_idempotency_key_ttl_expiry_creates_new_run() -> None:
    api = _build_api_without_init()
    store = RunStoreV2(max_runs=10)
    checkpoints = CheckpointManager(InMemoryCheckpointStoreBackend())

    def _fake_execute(*, skill_id, inputs, trace_id, **_kwargs):
        state = create_execution_state(skill_id, inputs or {}, trace_id=trace_id)
        mark_started(state)
        mark_finished(state, "completed")
        return SimpleNamespace(state=state), {
            "skill_id": skill_id,
            "status": "completed",
            "outputs": {"ok": True},
            "trace_id": trace_id,
        }

    api._execute_skill_with_result = _fake_execute  # type: ignore[attr-defined]

    with ThreadPoolExecutor(max_workers=1) as pool:
        first = api.execute_skill_async(
            skill_id="x.y",
            inputs={"n": 4},
            trace_id="t-idem-ttl",
            idempotency_key="idem-ttl-1",
            idempotency_ttl_seconds=3600,
            run_store=store,
            checkpoint_manager=checkpoints,
            async_pool=pool,
        )

        old_timestamp = "2000-01-01T00:00:00Z"
        store.patch_run(first["run_id"], {"created_at": old_timestamp})

        second = api.execute_skill_async(
            skill_id="x.y",
            inputs={"n": 4},
            trace_id="t-idem-ttl",
            idempotency_key="idem-ttl-1",
            idempotency_ttl_seconds=3600,
            run_store=store,
            checkpoint_manager=checkpoints,
            async_pool=pool,
        )

    assert first["run_id"] != second["run_id"]
    assert second.get("idempotent_replay") is not True


def test_execute_skill_async_idempotency_observability_counters() -> None:
    api = _build_api_without_init()
    store = RunStoreV2(max_runs=10)
    checkpoints = CheckpointManager(InMemoryCheckpointStoreBackend())

    before = METRICS.snapshot().get("counters", {})
    before_created = int(before.get("runtime.idempotency.created", 0))
    before_reused = int(before.get("runtime.idempotency.reused", 0))
    before_conflict = int(before.get("runtime.idempotency.conflict", 0))

    def _fake_execute(*, skill_id, inputs, trace_id, **_kwargs):
        state = create_execution_state(skill_id, inputs or {}, trace_id=trace_id)
        mark_started(state)
        mark_finished(state, "completed")
        return SimpleNamespace(state=state), {
            "skill_id": skill_id,
            "status": "completed",
            "outputs": {"ok": True},
            "trace_id": trace_id,
        }

    api._execute_skill_with_result = _fake_execute  # type: ignore[attr-defined]

    with ThreadPoolExecutor(max_workers=1) as pool:
        first = api.execute_skill_async(
            skill_id="x.y",
            inputs={"n": 10},
            trace_id="t-idem-metrics",
            idempotency_key="idem-metrics-1",
            run_store=store,
            checkpoint_manager=checkpoints,
            async_pool=pool,
        )

        replay = api.execute_skill_async(
            skill_id="x.y",
            inputs={"n": 10},
            trace_id="t-idem-metrics",
            idempotency_key="idem-metrics-1",
            run_store=store,
            checkpoint_manager=checkpoints,
            async_pool=pool,
        )

        conflict = api.execute_skill_async(
            skill_id="x.y",
            inputs={"n": 11},
            trace_id="t-idem-metrics",
            idempotency_key="idem-metrics-1",
            run_store=store,
            checkpoint_manager=checkpoints,
            async_pool=pool,
        )

        deadline = time.time() + 2.0
        while time.time() < deadline:
            run = store.get_run(first["run_id"])
            if isinstance(run, dict) and run.get("status") == "completed":
                break
            time.sleep(0.05)

    after = METRICS.snapshot().get("counters", {})
    after_created = int(after.get("runtime.idempotency.created", 0))
    after_reused = int(after.get("runtime.idempotency.reused", 0))
    after_conflict = int(after.get("runtime.idempotency.conflict", 0))

    assert replay.get("idempotent_replay") is True
    assert conflict["error"]["code"] == "idempotency_conflict"
    assert after_created - before_created >= 1
    assert after_reused - before_reused >= 1
    assert after_conflict - before_conflict >= 1


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


def test_replay_run_uses_unique_run_ids() -> None:
    api = _build_api_without_init()
    store = RunStoreV2(max_runs=10)
    checkpoints = CheckpointManager(InMemoryCheckpointStoreBackend())

    source_state = create_execution_state("x.y", {"n": 1}, trace_id="t-13")
    mark_started(source_state)
    source_state.vars["mid"] = "cached"
    record = checkpoints.save_checkpoint(
        run_id="r-replay-unique",
        state=source_state,
        step_id="s-1",
        kind="run_finished",
    )
    store.create_run_record(
        run_id="r-replay-unique",
        skill_id="x.y",
        trace_id="t-13",
        status="completed",
        checkpoint_head=record.checkpoint_id,
        metadata={"inputs": {"n": 1}, "execution_channel": "http-async"},
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
        first = api.replay_run(
            "r-replay-unique",
            run_store=store,
            checkpoint_manager=checkpoints,
            async_pool=pool,
        )
        second = api.replay_run(
            "r-replay-unique",
            run_store=store,
            checkpoint_manager=checkpoints,
            async_pool=pool,
        )

    assert first["ok"] is True
    assert second["ok"] is True
    assert first["data"]["run"]["run_id"] != second["data"]["run"]["run_id"]


def test_fork_run_creates_new_pending_run() -> None:
    api = _build_api_without_init()
    store = RunStoreV2(max_runs=10)
    checkpoints = CheckpointManager(InMemoryCheckpointStoreBackend())

    source_state = create_execution_state("x.y", {"n": 1}, trace_id="t-8")
    mark_started(source_state)
    record = checkpoints.save_checkpoint(
        run_id="r-fork-source",
        state=source_state,
        step_id="s-1",
        kind="run_finished",
    )
    store.create_run_record(
        run_id="r-fork-source",
        skill_id="x.y",
        trace_id="t-8",
        status="completed",
        checkpoint_head=record.checkpoint_id,
        metadata={"inputs": {"n": 1}, "execution_channel": "http-async"},
    )

    response = api.fork_run(
        "r-fork-source",
        run_store=store,
        checkpoint_manager=checkpoints,
    )

    assert response["ok"] is True
    fork_run = response["data"]["run"]
    assert fork_run["status"] == "pending"
    assert fork_run["metadata"]["source_run_id"] == "r-fork-source"
    assert fork_run["metadata"]["source_checkpoint_id"] == record.checkpoint_id
    assert fork_run["checkpoint_head"] == record.checkpoint_id


def test_fork_run_uses_unique_run_ids() -> None:
    api = _build_api_without_init()
    store = RunStoreV2(max_runs=10)
    checkpoints = CheckpointManager(InMemoryCheckpointStoreBackend())

    source_state = create_execution_state("x.y", {"n": 1}, trace_id="t-9")
    mark_started(source_state)
    record = checkpoints.save_checkpoint(
        run_id="r-fork-unique",
        state=source_state,
        step_id="s-1",
        kind="run_finished",
    )
    store.create_run_record(
        run_id="r-fork-unique",
        skill_id="x.y",
        trace_id="t-9",
        status="completed",
        checkpoint_head=record.checkpoint_id,
        metadata={"inputs": {"n": 1}, "execution_channel": "http-async"},
    )

    first = api.fork_run(
        "r-fork-unique",
        run_store=store,
        checkpoint_manager=checkpoints,
    )
    second = api.fork_run(
        "r-fork-unique",
        run_store=store,
        checkpoint_manager=checkpoints,
    )

    assert first["ok"] is True
    assert second["ok"] is True
    assert first["data"]["run"]["run_id"] != second["data"]["run"]["run_id"]


def test_fork_run_requires_checkpoint_head_or_checkpoint_id() -> None:
    api = _build_api_without_init()
    store = RunStoreV2(max_runs=10)
    checkpoints = CheckpointManager(InMemoryCheckpointStoreBackend())

    store.create_run_record(
        run_id="r-fork-missing",
        skill_id="x.y",
        trace_id="t-10",
        status="completed",
        metadata={"inputs": {"n": 1}, "execution_channel": "http-async"},
    )

    response = api.fork_run(
        "r-fork-missing",
        run_store=store,
        checkpoint_manager=checkpoints,
    )

    assert response["error"]["code"] == "invalid_request"


def test_resume_run_missing_run_returns_not_found() -> None:
    api = _build_api_without_init()
    store = RunStoreV2(max_runs=10)
    checkpoints = CheckpointManager(InMemoryCheckpointStoreBackend())

    response = api.resume_run(
        "r-does-not-exist",
        run_store=store,
        checkpoint_manager=checkpoints,
    )

    assert response["error"]["code"] == "not_found"
    assert response["error"]["status"] == 404


def test_replay_run_missing_checkpoint_returns_not_found() -> None:
    api = _build_api_without_init()
    store = RunStoreV2(max_runs=10)
    checkpoints = CheckpointManager(InMemoryCheckpointStoreBackend())

    store.create_run_record(
        run_id="r-replay-missing-checkpoint",
        skill_id="x.y",
        trace_id="t-11",
        status="completed",
        checkpoint_head="missing-checkpoint",
        metadata={"inputs": {"n": 1}, "execution_channel": "http-async"},
    )

    response = api.replay_run(
        "r-replay-missing-checkpoint",
        run_store=store,
        checkpoint_manager=checkpoints,
    )

    assert response["error"]["code"] == "not_found"
    assert response["error"]["status"] == 404


def test_fork_run_missing_checkpoint_returns_not_found() -> None:
    api = _build_api_without_init()
    store = RunStoreV2(max_runs=10)
    checkpoints = CheckpointManager(InMemoryCheckpointStoreBackend())

    source_state = create_execution_state("x.y", {"n": 1}, trace_id="t-12")
    mark_started(source_state)
    record = checkpoints.save_checkpoint(
        run_id="r-fork-missing-selected",
        state=source_state,
        step_id="s-1",
        kind="run_finished",
    )
    store.create_run_record(
        run_id="r-fork-missing-selected",
        skill_id="x.y",
        trace_id="t-12",
        status="completed",
        checkpoint_head=record.checkpoint_id,
        metadata={"inputs": {"n": 1}, "execution_channel": "http-async"},
    )

    response = api.fork_run(
        "r-fork-missing-selected",
        run_store=store,
        checkpoint_manager=checkpoints,
        checkpoint_id="missing-checkpoint",
    )

    assert response["error"]["code"] == "not_found"
    assert response["error"]["status"] == 404

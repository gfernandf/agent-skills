from __future__ import annotations

from runtime.checkpoint import state_to_dict
from runtime.checkpoint_manager import CheckpointManager, InMemoryCheckpointStoreBackend
from runtime.execution_state import (
    create_execution_state,
    emit_event,
    mark_started,
    mark_target_written,
    record_step_result,
)
from runtime.models import StepResult
from runtime.run_store import RunStore


def test_checkpoint_lineage_multi_boundary_roundtrip() -> None:
    backend = InMemoryCheckpointStoreBackend()
    manager = CheckpointManager(backend)

    state = create_execution_state(
        "durability.demo", {"text": "hello"}, trace_id="trace-1"
    )
    mark_started(state)
    emit_event(state, "skill_start", "start")

    manager.save_checkpoint(
        run_id="run-adv-1",
        state=state,
        step_id=None,
        kind="run_started",
        checkpoint_id="chk_start",
    )

    step_result = StepResult(
        step_id="step_1",
        uses="text.content.summarize",
        status="completed",
        resolved_input={"text": "hello"},
        produced_output={"summary": "hello"},
        started_at=None,
        finished_at=None,
    )
    record_step_result(state, step_result)
    state.vars["mid"] = "hello"
    mark_target_written(state, "vars.mid")
    emit_event(state, "step_completed", "step_1 done", step_id="step_1")

    manager.save_checkpoint(
        run_id="run-adv-1",
        state=state,
        step_id="step_1",
        kind="step_completed",
        pending_writes=["vars.mid"],
        checkpoint_id="chk_step_1",
    )

    state.status = "waiting_for_human"
    state.current_step = "step_2"
    emit_event(state, "waiting_for_human", "approval required", step_id="step_2")

    manager.save_checkpoint(
        run_id="run-adv-1",
        state=state,
        step_id="step_2",
        kind="waiting_for_human",
        pending_writes=["outputs.summary"],
        checkpoint_id="chk_wait",
    )

    records = manager.list_checkpoints("run-adv-1")
    assert len(records) == 3
    assert {item["checkpoint_id"] for item in records} == {
        "chk_start",
        "chk_step_1",
        "chk_wait",
    }

    loaded_state = manager.load_state(run_id="run-adv-1", checkpoint_id="chk_wait")
    assert loaded_state is not None
    assert state_to_dict(loaded_state) == state_to_dict(state)


def test_checkpoint_state_equivalence_after_partial_progress() -> None:
    backend = InMemoryCheckpointStoreBackend()
    manager = CheckpointManager(backend)

    state = create_execution_state("durability.demo", {"value": 1}, trace_id="trace-2")
    mark_started(state)

    record_step_result(
        state,
        StepResult(
            step_id="s1",
            uses="data.record.transform",
            status="completed",
            resolved_input={"value": 1},
            produced_output={"value": 2},
        ),
    )
    state.vars["v1"] = 2
    mark_target_written(state, "vars.v1")

    manager.save_checkpoint(
        run_id="run-adv-2",
        state=state,
        step_id="s1",
        kind="step_completed",
        checkpoint_id="chk_s1",
    )

    loaded = manager.load_state(run_id="run-adv-2", checkpoint_id="chk_s1")
    assert loaded is not None
    assert state_to_dict(loaded) == state_to_dict(state)


def test_resume_from_waiting_signal_uses_checkpoint_pointer() -> None:
    store = RunStore()
    store.create_run_record(run_id="run-adv-3", skill_id="skill.demo", status="pending")
    running = store.update_status("run-adv-3", "running", checkpoint_head="chk_001")
    assert running is not None

    waiting = store.update_status(
        "run-adv-3",
        "waiting_for_signal",
        checkpoint_head="chk_002",
        current_step_id="wait_step",
    )
    assert waiting is not None
    assert waiting["status"] == "waiting_for_signal"
    assert waiting["checkpoint_head"] == "chk_002"

    resumed = store.resume_run("run-adv-3", resume_from_checkpoint_id="chk_002")
    assert resumed is not None
    assert resumed["status"] == "running"
    assert resumed["resume_from_checkpoint_id"] == "chk_002"
    assert resumed["checkpoint_head"] == "chk_002"


def test_replay_and_fork_preserve_lineage_metadata_integrity() -> None:
    store = RunStore()

    replay = store.replay_run(
        "replay-adv-1",
        skill_id="skill.demo",
        source_run_id="source-1",
        source_checkpoint_id="chk-source-1",
        checkpoint_head="chk-source-1",
        metadata={"tenant": "tenant-1"},
    )
    assert replay["status"] == "replaying"
    assert replay["metadata"]["source_run_id"] == "source-1"
    assert replay["metadata"]["source_checkpoint_id"] == "chk-source-1"
    assert replay["metadata"]["replay_mode"] == "checkpoint_replay"

    fork = store.fork_run(
        "fork-adv-1",
        skill_id="skill.demo",
        source_run_id="source-1",
        source_checkpoint_id="chk-source-2",
        checkpoint_head="chk-source-2",
        metadata={"tenant": "tenant-1"},
    )
    assert fork["status"] == "pending"
    assert fork["metadata"]["source_run_id"] == "source-1"
    assert fork["metadata"]["source_checkpoint_id"] == "chk-source-2"
    assert fork["metadata"]["fork_mode"] == "checkpoint_fork"
    assert replay["run_id"] != fork["run_id"]

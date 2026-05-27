"""Tests for runtime/checkpoint_manager.py.

Run: python -m runtime.test_checkpoint_manager
"""

from __future__ import annotations

import sys

from runtime.checkpoint_manager import CheckpointManager, InMemoryCheckpointStoreBackend
from runtime.execution_state import create_execution_state


_pass = 0
_fail = 0


def _test(label: str, condition: bool) -> None:
    global _pass, _fail
    if condition:
        _pass += 1
    else:
        _fail += 1
        print(f"  FAIL: {label}")


def test_save_and_load_state() -> None:
    backend = InMemoryCheckpointStoreBackend()
    manager = CheckpointManager(backend)

    state = create_execution_state("demo.skill", {"text": "hello"}, trace_id="t1")
    state.status = "running"
    state.current_step = "step_a"

    record = manager.save_checkpoint(
        run_id="run-1",
        state=state,
        step_id="step_a",
        kind="step_completed",
        pending_writes=["outputs.summary"],
    )
    _test(
        "record id exists",
        isinstance(record.checkpoint_id, str) and len(record.checkpoint_id) > 0,
    )
    _test("record run id", record.run_id == "run-1")

    loaded_state = manager.load_state(
        run_id="run-1", checkpoint_id=record.checkpoint_id
    )
    _test("load state exists", loaded_state is not None)
    _test(
        "load state skill",
        loaded_state is not None and loaded_state.skill_id == "demo.skill",
    )
    _test(
        "load state current_step",
        loaded_state is not None and loaded_state.current_step == "step_a",
    )


def test_list_checkpoints() -> None:
    backend = InMemoryCheckpointStoreBackend()
    manager = CheckpointManager(backend)
    state = create_execution_state("demo.skill", {})

    manager.save_checkpoint(
        run_id="run-2", state=state, step_id="a", kind="step_completed"
    )
    manager.save_checkpoint(
        run_id="run-2", state=state, step_id="b", kind="step_completed"
    )
    records = manager.list_checkpoints("run-2")
    _test("list count", len(records) == 2)
    _test(
        "list has ids",
        all(isinstance(item.get("checkpoint_id"), str) for item in records),
    )


def main() -> None:
    test_save_and_load_state()
    test_list_checkpoints()
    print(f"\n  checkpoint_manager: {_pass} passed, {_fail} failed")
    if _fail:
        sys.exit(1)


if __name__ == "__main__":
    main()

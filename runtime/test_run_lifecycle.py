"""Tests for runtime/run_lifecycle.py.

Run: python -m runtime.test_run_lifecycle
"""

from __future__ import annotations

import sys

from runtime.run_lifecycle import RunStateMachine


_pass = 0
_fail = 0


def _test(label: str, condition: bool) -> None:
    global _pass, _fail
    if condition:
        _pass += 1
    else:
        _fail += 1
        print(f"  FAIL: {label}")


def test_status_validation() -> None:
    sm = RunStateMachine()
    _test("valid status running", sm.is_valid_status("running"))
    _test("invalid status unknown", not sm.is_valid_status("banana"))


def test_valid_transitions() -> None:
    sm = RunStateMachine()
    _test(
        "pending->running",
        sm.can_transition("pending", "running").allowed,
    )
    _test(
        "running->waiting_for_human",
        sm.can_transition("running", "waiting_for_human").allowed,
    )
    _test(
        "waiting_for_human->running",
        sm.can_transition("waiting_for_human", "running").allowed,
    )
    _test(
        "running->completed",
        sm.can_transition("running", "completed").allowed,
    )


def test_invalid_transitions() -> None:
    sm = RunStateMachine()
    _test(
        "completed->running invalid",
        not sm.can_transition("completed", "running").allowed,
    )
    _test(
        "failed->running invalid",
        not sm.can_transition("failed", "running").allowed,
    )
    _test(
        "running->pending invalid",
        not sm.can_transition("running", "pending").allowed,
    )


def main() -> None:
    test_status_validation()
    test_valid_transitions()
    test_invalid_transitions()
    print(f"\n  run_lifecycle: {_pass} passed, {_fail} failed")
    if _fail:
        sys.exit(1)


if __name__ == "__main__":
    main()

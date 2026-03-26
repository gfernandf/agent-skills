"""
Tests for runtime.run_store — async execution tracking.

Run: python -m runtime.test_run_store
"""

from __future__ import annotations

import sys
import threading

from runtime.run_store import RunStore


_pass = 0
_fail = 0


def _test(label: str, condition: bool, detail: str = "") -> None:
    global _pass, _fail
    if condition:
        _pass += 1
    else:
        _fail += 1
        msg = f"  FAIL: {label}"
        if detail:
            msg += f" — {detail}"
        print(msg)


def test_create_run():
    store = RunStore()
    run = store.create_run("r1", "my.skill", trace_id="t1")
    _test("create: run_id", run["run_id"] == "r1")
    _test("create: skill_id", run["skill_id"] == "my.skill")
    _test("create: status running", run["status"] == "running")
    _test("create: trace_id", run["trace_id"] == "t1")
    _test("create: created_at present", run["created_at"] is not None)
    _test("create: result None", run["result"] is None)


def test_get_run():
    store = RunStore()
    store.create_run("r1", "my.skill")
    run = store.get_run("r1")
    _test("get: found", run is not None)
    _test("get: correct id", run["run_id"] == "r1")
    _test("get: missing returns None", store.get_run("r999") is None)


def test_complete_run():
    store = RunStore()
    store.create_run("r1", "my.skill")
    store.complete_run("r1", {"status": "completed", "outputs": {"x": 1}})
    run = store.get_run("r1")
    _test("complete: status", run["status"] == "completed")
    _test("complete: finished_at", run["finished_at"] is not None)
    _test("complete: result", run["result"]["outputs"]["x"] == 1)


def test_fail_run():
    store = RunStore()
    store.create_run("r1", "my.skill")
    store.fail_run("r1", "something broke")
    run = store.get_run("r1")
    _test("fail: status", run["status"] == "failed")
    _test("fail: error", run["error"] == "something broke")
    _test("fail: finished_at", run["finished_at"] is not None)


def test_list_runs():
    store = RunStore()
    store.create_run("r1", "skill.a")
    store.create_run("r2", "skill.b")
    store.create_run("r3", "skill.c")
    runs = store.list_runs(limit=10)
    _test("list: count", len(runs) == 3)
    _test("list: newest first", runs[0]["run_id"] == "r3")
    _test("list: oldest last", runs[2]["run_id"] == "r1")

    limited = store.list_runs(limit=2)
    _test("list: limit works", len(limited) == 2)


def test_eviction():
    store = RunStore(max_runs=3)
    store.create_run("r1", "s")
    store.create_run("r2", "s")
    store.create_run("r3", "s")
    store.create_run("r4", "s")
    _test("evict: oldest removed", store.get_run("r1") is None)
    _test("evict: newest present", store.get_run("r4") is not None)
    runs = store.list_runs()
    _test("evict: count capped", len(runs) == 3)


def test_thread_safety():
    store = RunStore(max_runs=500)
    errors = []

    def create_batch(start: int):
        try:
            for i in range(100):
                store.create_run(f"r{start + i}", "s")
        except Exception as e:
            errors.append(str(e))

    threads = [threading.Thread(target=create_batch, args=(i * 100,)) for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    _test("thread_safety: no errors", len(errors) == 0)
    runs = store.list_runs(limit=500)
    _test("thread_safety: runs present", len(runs) > 0)


def test_complete_missing_run():
    """Completing a non-existent run should not raise."""
    store = RunStore()
    store.complete_run("nonexistent", {"status": "completed"})
    _test("complete_missing: no error", True)


def main():
    global _pass, _fail

    test_create_run()
    test_get_run()
    test_complete_run()
    test_fail_run()
    test_list_runs()
    test_eviction()
    test_thread_safety()
    test_complete_missing_run()

    print(f"\n  run_store: {_pass} passed, {_fail} failed")
    if _fail:
        sys.exit(1)


if __name__ == "__main__":
    main()

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
    _test("create: thread_id default None", run.get("thread_id") is None)
    _test("create: versions default mapping", isinstance(run.get("versions"), dict))


def test_create_run_record_v2():
    store = RunStore()
    run = store.create_run_record(
        run_id="rv2",
        skill_id="my.skill",
        trace_id="tv2",
        status="pending",
        thread_id="thr-1",
        skill_version="0.3.1",
        tenant_id="tenant-1",
        environment="prod",
        versions={"registry_ref": "git:abc123"},
    )
    _test("create_v2: status pending", run["status"] == "pending")
    _test("create_v2: thread_id", run["thread_id"] == "thr-1")
    _test("create_v2: skill_version", run["skill_version"] == "0.3.1")
    _test("create_v2: tenant", run["tenant_id"] == "tenant-1")
    _test("create_v2: env", run["environment"] == "prod")
    _test(
        "create_v2: registry_ref",
        run.get("versions", {}).get("registry_ref") == "git:abc123",
    )


def test_status_transitions_v2():
    store = RunStore()
    store.create_run_record(run_id="rsm", skill_id="my.skill", status="pending")
    running = store.update_status("rsm", "running")
    _test("transition pending->running", running is not None and running["status"] == "running")

    waiting = store.mark_waiting_for_human(
        "rsm",
        current_step_id="send_email",
        checkpoint_head="chk_001",
        approval_request={"reason": "requires_confirmation"},
    )
    _test(
        "transition running->waiting_for_human",
        waiting is not None and waiting["status"] == "waiting_for_human",
    )

    resumed = store.resume_run("rsm", resume_from_checkpoint_id="chk_001")
    _test(
        "transition waiting_for_human->running",
        resumed is not None and resumed["status"] == "running",
    )


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


def test_pagination_and_status_filter():
    store = RunStore()
    store.create_run("r1", "skill")
    store.create_run("r2", "skill")
    store.create_run("r3", "skill")
    store.complete_run("r1", {"ok": True})
    store.fail_run("r2", "boom")

    page = store.list_runs_page(limit=2, offset=0)
    _test("page: size", len(page) == 2)
    _test("page: newest first", page[0]["run_id"] == "r3")

    completed = store.list_runs_page(limit=10, status="completed")
    _test("status filter: completed count", len(completed) == 1)
    _test("status filter: completed id", completed[0]["run_id"] == "r1")

    running_count = store.count_runs(status="running")
    _test("count running", running_count == 1)
    all_count = store.count_runs()
    _test("count all", all_count == 3)


def test_cancel_run():
    store = RunStore()
    store.create_run("r1", "skill")
    canceled = store.cancel_run("r1")
    _test("cancel: returns run", isinstance(canceled, dict))
    _test("cancel: status canceled", canceled["status"] == "canceled")
    _test("cancel: has error reason", "Canceled by client" in (canceled["error"] or ""))

    missing = store.cancel_run("missing")
    _test("cancel missing returns None", missing is None)


def main():
    global _pass, _fail

    test_create_run()
    test_create_run_record_v2()
    test_status_transitions_v2()
    test_get_run()
    test_complete_run()
    test_fail_run()
    test_list_runs()
    test_eviction()
    test_thread_safety()
    test_complete_missing_run()
    test_pagination_and_status_filter()
    test_cancel_run()

    print(f"\n  run_store: {_pass} passed, {_fail} failed")
    if _fail:
        sys.exit(1)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _load_trace_ids(runtime_root: Path) -> set[str]:
    trace_ids: set[str] = set()
    audit_file = runtime_root / "artifacts" / "runtime_skill_audit.jsonl"
    if not audit_file.exists():
        return trace_ids

    with audit_file.open("r", encoding="utf-8") as f:
        for line in f:
            raw = line.strip()
            if not raw:
                continue
            try:
                item = json.loads(raw)
            except Exception:
                continue
            if not isinstance(item, dict):
                continue
            trace_id = item.get("trace_id")
            if isinstance(trace_id, str) and trace_id:
                trace_ids.add(trace_id)

    return trace_ids


def _load_task_ids(runtime_root: Path) -> set[str]:
    task_ids: set[str] = set()
    tasks_file = runtime_root / "artifacts" / "attach_targets" / "tasks.json"
    if not tasks_file.exists():
        return task_ids

    try:
        raw: Any = json.loads(tasks_file.read_text(encoding="utf-8"))
    except Exception:
        return task_ids

    if isinstance(raw, dict):
        values = raw.get("task_ids")
        if isinstance(values, list):
            for item in values:
                if isinstance(item, str) and item:
                    task_ids.add(item)
    elif isinstance(raw, list):
        for item in raw:
            if isinstance(item, str) and item:
                task_ids.add(item)

    return task_ids


def _load_artifact_file_refs(runtime_root: Path) -> set[str]:
    refs: set[str] = set()
    artifacts_root = runtime_root / "artifacts"
    if not artifacts_root.exists():
        return refs

    for p in artifacts_root.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(runtime_root).as_posix()
        refs.add(rel)

    return refs


def build_index(runtime_root: Path, output_path: Path | None = None) -> Path:
    trace_ids = _load_trace_ids(runtime_root)
    task_ids = _load_task_ids(runtime_root)
    artifact_paths = _load_artifact_file_refs(runtime_root)

    targets: dict[str, list[str]] = {
        "run": sorted(trace_ids),
        "output": sorted(trace_ids),
        "transcript": sorted(trace_ids),
        "artifact": sorted(set(trace_ids).union(artifact_paths)),
        "task": sorted(task_ids),
    }

    payload = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source": {
            "runtime_audit": "artifacts/runtime_skill_audit.jsonl",
            "tasks": "artifacts/attach_targets/tasks.json",
            "artifacts_root": "artifacts/",
        },
        "targets": targets,
    }

    out = output_path or (runtime_root / "artifacts" / "attach_targets" / "index.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return out


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build attach target index from runtime artifacts."
    )
    parser.add_argument(
        "--runtime-root", type=Path, default=Path(__file__).resolve().parent.parent
    )
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    runtime_root = args.runtime_root.resolve()
    output = args.output.resolve() if args.output is not None else None

    out = build_index(runtime_root, output)
    print(f"ATTACH TARGET INDEX GENERATED: {out.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                rows.append(item)
    return rows


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def build_usage(log_file: Path) -> dict[str, Any]:
    events = _read_jsonl(log_file)

    exec_total: dict[str, int] = defaultdict(int)
    success_total: dict[str, int] = defaultdict(int)
    timeout_total: dict[str, int] = defaultdict(int)
    durations: dict[str, list[float]] = defaultdict(list)

    for event in events:
        event_name = event.get("event")
        skill_id = event.get("skill_id")
        if not isinstance(skill_id, str) or not skill_id:
            continue

        if event_name == "skill.execute.completed":
            exec_total[skill_id] += 1
            success_total[skill_id] += 1
            duration_ms = event.get("duration_ms")
            if isinstance(duration_ms, (int, float)):
                durations[skill_id].append(float(duration_ms))

        elif event_name == "skill.execute.failed":
            exec_total[skill_id] += 1
            reason = str(event.get("reason", "")).lower()
            if "timeout" in reason:
                timeout_total[skill_id] += 1

    skills: dict[str, dict[str, Any]] = {}
    for skill_id, executions in sorted(exec_total.items()):
        ds = sorted(durations.get(skill_id, []))

        p50 = None
        p95 = None
        if ds:
            p50 = ds[len(ds) // 2]
            p95 = ds[min(len(ds) - 1, int(round((len(ds) - 1) * 0.95)))]

        skills[skill_id] = {
            "executions_30d": executions,
            "successes_30d": success_total.get(skill_id, 0),
            "timeouts_30d": timeout_total.get(skill_id, 0),
            "p50_duration_ms": round(p50, 3) if isinstance(p50, float) else p50,
            "p95_duration_ms": round(p95, 3) if isinstance(p95, float) else p95,
        }

    return {"skills": skills}


def main() -> int:
    parser = argparse.ArgumentParser(prog="ingest_skill_usage_from_logs")
    parser.add_argument(
        "--log-file",
        type=Path,
        required=True,
        help="JSONL log file with runtime events",
    )
    parser.add_argument(
        "--out", type=Path, default=Path("artifacts") / "skill_usage_30d.json"
    )
    args = parser.parse_args()

    if not args.log_file.exists():
        print(f"USAGE INGEST FAILED: missing log file '{args.log_file}'.")
        return 1

    usage = build_usage(args.log_file)
    _write_json(args.out, usage)

    print("Skill usage ingestion completed.")
    print(f"Skills: {len(usage['skills'])}")
    print(f"Written: {args.out.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

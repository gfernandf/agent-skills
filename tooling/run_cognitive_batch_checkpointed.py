#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import tooling.verify_cognitive_pure_stability_matrix as m

ROOT = Path(__file__).resolve().parent.parent
OUT_ROOT = ROOT / "artifacts" / "cognitive_stability"
RUNS_ROOT = OUT_ROOT / "_runs"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _save_json(path: Path, data: Any) -> None:
    _ensure_dir(path.parent)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def _cap_report_path(capability_id: str) -> Path:
    namespace = capability_id.split(".")[0]
    return OUT_ROOT / f"remote_{namespace}" / f"{capability_id}.json"


def _compute_summary(results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    stable: list[str] = []
    unstable: list[str] = []
    skipped: list[str] = []

    for cid, rep in results.items():
        status = str(rep.get("status", ""))
        if status != "ok":
            skipped.append(cid)
            continue
        assessment = rep.get("overall_assessment") or {}
        if bool(assessment.get("stable")):
            stable.append(cid)
        else:
            unstable.append(cid)

    return {
        "total": len(results),
        "stable": len(stable),
        "unstable": len(unstable),
        "skipped": len(skipped),
        "stable_ids": stable,
        "unstable_ids": unstable,
        "skipped_ids": skipped,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a cognitive capability slice with per-capability checkpoints and resume support."
        )
    )
    parser.add_argument(
        "--start", type=int, required=True, help="Slice start index (inclusive)"
    )
    parser.add_argument(
        "--end", type=int, required=True, help="Slice end index (exclusive)"
    )
    parser.add_argument(
        "--run-name",
        type=str,
        default="",
        help="Optional run name; default is auto-generated from timestamp and slice",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from existing progress file for this run",
    )
    parser.add_argument(
        "--allow-remote-openapi",
        action="store_true",
        help="Allow remote OpenAPI calls (passed through to verifier)",
    )
    parser.add_argument(
        "--stop-on-error",
        action="store_true",
        help="Stop immediately when one capability raises an exception",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.start < 0 or args.end <= args.start:
        raise SystemExit("Invalid slice. Use --start >= 0 and --end > --start.")

    docs = m._read_capability_docs()
    selected = docs[args.start : args.end]
    if not selected:
        raise SystemExit("Selected slice is empty.")

    run_name = args.run_name.strip()
    if not run_name:
        run_name = (
            f"{_now_iso().replace(':', '').replace('-', '')}_{args.start}_{args.end}"
        )

    run_dir = RUNS_ROOT / run_name
    progress_path = run_dir / "progress.json"
    summary_path = run_dir / "summary.json"
    journal_path = run_dir / "journal.jsonl"

    _ensure_dir(run_dir)

    progress = _load_json(
        progress_path,
        {
            "run_name": run_name,
            "started_at": _now_iso(),
            "updated_at": _now_iso(),
            "slice": {"start": args.start, "end": args.end},
            "allow_remote_openapi": bool(args.allow_remote_openapi),
            "completed": [],
            "failed": [],
            "results": {},
        },
    )

    if not args.resume and progress_path.exists():
        raise SystemExit(
            "Run already exists. Use --resume to continue or choose another --run-name."
        )

    if args.resume:
        existing_slice = progress.get("slice") or {}
        if (
            int(existing_slice.get("start", -1)) != args.start
            or int(existing_slice.get("end", -1)) != args.end
        ):
            raise SystemExit("Slice does not match existing run progress.")

    completed: set[str] = set(progress.get("completed") or [])
    failed: set[str] = set(progress.get("failed") or [])
    results: dict[str, dict[str, Any]] = dict(progress.get("results") or {})

    casepacks = m._load_casepacks(
        Path("tooling/stability_casepacks/cognitive_pure_casepacks.yaml")
    )
    registry = m.BindingRegistry(repo_root=m.ROOT, host_root=m.ROOT)

    for raw_cap in selected:
        capability_id = str(raw_cap.get("id"))
        if capability_id in completed:
            continue

        start_at = _now_iso()
        print(f"RUN {capability_id} start={start_at}", flush=True)

        try:
            report = m._run_for_capability(
                raw_capability=raw_cap,
                casepacks=casepacks,
                registry=registry,
                allow_remote_openapi=bool(args.allow_remote_openapi),
            )
            results[capability_id] = report
            completed.add(capability_id)
            if capability_id in failed:
                failed.remove(capability_id)

            out_path = _cap_report_path(capability_id)
            _save_json(out_path, report)

            row = {
                "ts": _now_iso(),
                "capability_id": capability_id,
                "status": "ok",
                "stable": bool((report.get("overall_assessment") or {}).get("stable")),
                "report_path": str(out_path),
            }
            journal_path.write_text(
                "", encoding="utf-8"
            ) if not journal_path.exists() else None
            with journal_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

        except KeyboardInterrupt:
            print("INTERRUPTED: saving checkpoint...", flush=True)
            progress.update(
                {
                    "updated_at": _now_iso(),
                    "completed": sorted(completed),
                    "failed": sorted(failed),
                    "results": results,
                }
            )
            _save_json(progress_path, progress)
            _save_json(summary_path, _compute_summary(results))
            raise
        except Exception as exc:
            failed.add(capability_id)
            row = {
                "ts": _now_iso(),
                "capability_id": capability_id,
                "status": "error",
                "error": f"{type(exc).__name__}: {exc}",
            }
            journal_path.write_text(
                "", encoding="utf-8"
            ) if not journal_path.exists() else None
            with journal_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            print(f"ERROR {capability_id}: {row['error']}", flush=True)
            if args.stop_on_error:
                progress.update(
                    {
                        "updated_at": _now_iso(),
                        "completed": sorted(completed),
                        "failed": sorted(failed),
                        "results": results,
                    }
                )
                _save_json(progress_path, progress)
                _save_json(summary_path, _compute_summary(results))
                return 1

        progress.update(
            {
                "updated_at": _now_iso(),
                "completed": sorted(completed),
                "failed": sorted(failed),
                "results": results,
            }
        )
        _save_json(progress_path, progress)
        _save_json(summary_path, _compute_summary(results))

    progress.update(
        {
            "finished_at": _now_iso(),
            "updated_at": _now_iso(),
            "completed": sorted(completed),
            "failed": sorted(failed),
            "results": results,
        }
    )
    _save_json(progress_path, progress)

    summary = _compute_summary(results)
    _save_json(summary_path, summary)

    print("DONE", flush=True)
    print(json.dumps({"run_name": run_name, **summary}, ensure_ascii=False), flush=True)

    return 0 if summary["unstable"] == 0 and summary["skipped"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

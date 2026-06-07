#!/usr/bin/env python3
"""Incremental runner for cognitive stability verification with durable checkpoints.

This script wraps tooling.verify_cognitive_pure_stability_matrix and persists progress
per capability so interrupted runs can be resumed without losing completed work.
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tooling.verify_cognitive_pure_stability_matrix as matrix
DEFAULT_OUT_DIR = ROOT / "artifacts" / "cognitive_stability"
DEFAULT_STATE_FILE = ROOT / "artifacts" / "cognitive_stability_incremental_state.json"
DEFAULT_MATRIX_FILE = ROOT / "artifacts" / "cognitive_stability_incremental_matrix.json"
DEFAULT_CASEPACK_FILE = ROOT / "tooling" / "stability_casepacks" / "cognitive_pure_casepacks.yaml"


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except Exception:
        return str(path)


def _json_dump(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return raw if isinstance(raw, dict) else None


def _build_capability_scope(args: argparse.Namespace) -> list[dict[str, Any]]:
    raw_caps = matrix._read_capability_docs()
    raw_caps = sorted(raw_caps, key=lambda c: str(c.get("id", "")))

    if args.capability_prefix:
        raw_caps = [c for c in raw_caps if str(c.get("id", "")).startswith(args.capability_prefix)]

    if args.capability_ids:
        wanted = {item.strip() for item in args.capability_ids if item.strip()}
        raw_caps = [c for c in raw_caps if str(c.get("id", "")) in wanted]

    if args.start_index is not None or args.end_index is not None:
        start = args.start_index or 0
        end = args.end_index if args.end_index is not None else len(raw_caps)
        raw_caps = raw_caps[start:end]

    if args.max_capabilities and args.max_capabilities > 0:
        raw_caps = raw_caps[: args.max_capabilities]

    return raw_caps


def _default_state(args: argparse.Namespace, capability_ids: list[str]) -> dict[str, Any]:
    return {
        "version": 1,
        "created_at": _iso_now(),
        "updated_at": _iso_now(),
        "config": {
            "out_dir": str(args.out_dir),
            "matrix_file": str(args.matrix_file),
            "casepack_file": str(args.casepack_file),
            "capability_prefix": args.capability_prefix or None,
            "capability_ids": args.capability_ids,
            "start_index": args.start_index,
            "end_index": args.end_index,
            "max_capabilities": args.max_capabilities,
            "allow_remote_openapi": bool(args.allow_remote_openapi),
            "semantic_strict": bool(args.semantic_strict),
            "semantic_min_pass_rate": float(args.semantic_min_pass_rate),
            "require_semantic_casepack": bool(args.require_semantic_casepack),
        },
        "capability_order": capability_ids,
        "capabilities": {},
    }


def _reconcile_state(
    existing: dict[str, Any] | None,
    *,
    args: argparse.Namespace,
    capability_ids: list[str],
) -> dict[str, Any]:
    if args.reset or existing is None:
        return _default_state(args, capability_ids)

    state = dict(existing)
    state.setdefault("version", 1)
    state.setdefault("created_at", _iso_now())
    state["updated_at"] = _iso_now()
    state["config"] = {
        "out_dir": str(args.out_dir),
        "matrix_file": str(args.matrix_file),
        "casepack_file": str(args.casepack_file),
        "capability_prefix": args.capability_prefix or None,
        "capability_ids": args.capability_ids,
        "start_index": args.start_index,
        "end_index": args.end_index,
        "max_capabilities": args.max_capabilities,
        "allow_remote_openapi": bool(args.allow_remote_openapi),
        "semantic_strict": bool(args.semantic_strict),
        "semantic_min_pass_rate": float(args.semantic_min_pass_rate),
        "require_semantic_casepack": bool(args.require_semantic_casepack),
    }
    state["capability_order"] = capability_ids
    state.setdefault("capabilities", {})
    return state


def _capability_status(report: dict[str, Any]) -> str:
    if report.get("status") != "ok":
        return str(report.get("status") or "error")
    overall = report.get("overall_assessment") if isinstance(report.get("overall_assessment"), dict) else {}
    if overall.get("stable") is True:
        return "stable"
    return "unstable"


def _entry_from_report(report: dict[str, Any], report_path: Path) -> dict[str, Any]:
    status = _capability_status(report)
    overall = report.get("overall_assessment") if isinstance(report.get("overall_assessment"), dict) else {}
    findings = overall.get("findings") if isinstance(overall.get("findings"), list) else []
    return {
        "status": status,
        "updated_at": _iso_now(),
        "report_path": str(report_path),
        "report": report,
        "finding_count": len(findings),
    }


def _entry_from_exception(exc: BaseException) -> dict[str, Any]:
    return {
        "status": "error",
        "updated_at": _iso_now(),
        "error_type": type(exc).__name__,
        "error_message": str(exc),
        "traceback": traceback.format_exc(),
    }


def _seed_state_from_existing_reports(
    *,
    state: dict[str, Any],
    out_dir: Path,
    capability_ids: list[str],
) -> int:
    if not out_dir.exists():
        return 0

    capabilities_state = state.setdefault("capabilities", {})
    wanted = set(capability_ids)
    report_candidates: dict[str, Path] = {}

    for path in sorted(out_dir.rglob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(raw, dict):
            continue
        capability_id = raw.get("capability_id")
        if not isinstance(capability_id, str) or capability_id not in wanted:
            continue
        if capability_id in report_candidates:
            continue
        report_candidates[capability_id] = path

    seeded = 0
    for capability_id in capability_ids:
        if capability_id in capabilities_state:
            continue
        report_path = report_candidates.get(capability_id)
        if report_path is None:
            continue
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(report, dict):
            continue
        capabilities_state[capability_id] = _entry_from_report(report, report_path)
        seeded += 1

    if seeded:
        state["updated_at"] = _iso_now()
    return seeded


def _write_matrix_snapshot(
    *,
    state: dict[str, Any],
    matrix_file: Path,
) -> dict[str, Any]:
    order = state.get("capability_order") if isinstance(state.get("capability_order"), list) else []
    capabilities = state.get("capabilities") if isinstance(state.get("capabilities"), dict) else {}

    counts: Counter[str] = Counter()
    category_counts: Counter[str] = Counter()
    reports: list[dict[str, Any]] = []

    for capability_id in order:
        entry = capabilities.get(capability_id)
        if not isinstance(entry, dict):
            counts["pending"] += 1
            reports.append({"capability_id": capability_id, "status": "pending"})
            continue

        status = str(entry.get("status") or "pending")
        counts[status] += 1
        report = entry.get("report") if isinstance(entry.get("report"), dict) else None
        if report is None:
            reports.append(
                {
                    "capability_id": capability_id,
                    "status": status,
                    "error_type": entry.get("error_type"),
                    "error_message": entry.get("error_message"),
                }
            )
            continue

        overall = report.get("overall_assessment") if isinstance(report.get("overall_assessment"), dict) else {}
        findings = overall.get("findings") if isinstance(overall.get("findings"), list) else []
        for finding in findings:
            if isinstance(finding, dict):
                category = finding.get("category")
                if isinstance(category, str) and category:
                    category_counts[category] += 1

        reports.append(
            {
                "capability_id": capability_id,
                "status": status,
                "overall_assessment": overall,
                "bindings": report.get("bindings"),
                "report_path": entry.get("report_path"),
            }
        )

    payload = {
        "generated_at": _iso_now(),
        "runner": "cognitive_stability_incremental_v1",
        "state_file": str(state.get("state_file")) if state.get("state_file") else None,
        "summary": {
            "stable": counts.get("stable", 0),
            "unstable": counts.get("unstable", 0),
            "skipped": counts.get("skipped", 0),
            "error": counts.get("error", 0),
            "pending": counts.get("pending", 0),
            "finding_categories": dict(category_counts),
        },
        "scope": {
            "capabilities_considered": len(order),
            "allow_remote_openapi": bool((state.get("config") or {}).get("allow_remote_openapi")),
        },
        "capability_reports": reports,
    }
    _json_dump(matrix_file, payload)
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run cognitive stability verification incrementally with checkpoints and resume support"
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=DEFAULT_OUT_DIR,
        help=f"Per-capability report directory (default: {_safe_rel(DEFAULT_OUT_DIR)})",
    )
    parser.add_argument(
        "--state-file",
        type=Path,
        default=DEFAULT_STATE_FILE,
        help=f"Incremental state file (default: {_safe_rel(DEFAULT_STATE_FILE)})",
    )
    parser.add_argument(
        "--matrix-file",
        type=Path,
        default=DEFAULT_MATRIX_FILE,
        help=f"Incremental matrix snapshot (default: {_safe_rel(DEFAULT_MATRIX_FILE)})",
    )
    parser.add_argument(
        "--casepack-file",
        type=Path,
        default=DEFAULT_CASEPACK_FILE,
        help=f"Optional casepack YAML (default: {_safe_rel(DEFAULT_CASEPACK_FILE)})",
    )
    parser.add_argument(
        "--capability-prefix",
        type=str,
        default="",
        help="Optional prefix filter (e.g. reasoning. or decision.)",
    )
    parser.add_argument(
        "--capability-id",
        dest="capability_ids",
        action="append",
        default=[],
        help="Explicit capability id to include; may be repeated",
    )
    parser.add_argument(
        "--start-index",
        type=int,
        default=None,
        help="Optional inclusive start index after filtering",
    )
    parser.add_argument(
        "--end-index",
        type=int,
        default=None,
        help="Optional exclusive end index after filtering",
    )
    parser.add_argument(
        "--max-capabilities",
        type=int,
        default=0,
        help="Optional max capabilities to process after filtering (0 = no limit)",
    )
    parser.add_argument(
        "--allow-remote-openapi",
        action="store_true",
        help="Run OpenAPI lane even when service appears remote/external",
    )
    parser.add_argument(
        "--semantic-strict",
        action="store_true",
        help="Require semantic checks on every evaluated case",
    )
    parser.add_argument(
        "--semantic-min-pass-rate",
        type=float,
        default=0.8,
        help="Minimum semantic pass rate per lane (default: 0.8)",
    )
    parser.add_argument(
        "--require-semantic-casepack",
        action="store_true",
        help="Fail capability assessment when any case lacks semantic expected_signals",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from existing state file and skip completed capabilities",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Ignore existing state and create a fresh checkpoint set",
    )
    parser.add_argument(
        "--rerun-status",
        action="append",
        default=[],
        help="Statuses to rerun on resume, e.g. unstable, error, skipped",
    )
    parser.add_argument(
        "--stop-on-error",
        action="store_true",
        help="Stop immediately if a capability raises an unexpected exception",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Process at most N capabilities in this invocation after resume filtering (0 = no limit)",
    )
    parser.add_argument(
        "--skip-seed-existing",
        action="store_true",
        help="Do not preload existing per-capability reports from artifacts into the incremental state",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.resume and args.reset:
        raise SystemExit("--resume and --reset are mutually exclusive")
    if args.start_index is not None and args.start_index < 0:
        raise SystemExit("--start-index must be >= 0")
    if args.end_index is not None and args.end_index < 0:
        raise SystemExit("--end-index must be >= 0")
    if args.end_index is not None and args.start_index is not None and args.end_index < args.start_index:
        raise SystemExit("--end-index must be >= --start-index")

    raw_caps = _build_capability_scope(args)
    capability_ids = [str(cap.get("id")) for cap in raw_caps]

    existing_state = _load_json(args.state_file)
    state = _reconcile_state(existing_state if args.resume else None, args=args, capability_ids=capability_ids)
    state["state_file"] = str(args.state_file)

    seeded_count = 0
    if not args.skip_seed_existing:
        seeded_count = _seed_state_from_existing_reports(
            state=state,
            out_dir=args.out_dir,
            capability_ids=capability_ids,
        )

    rerun_statuses = {item.strip().lower() for item in args.rerun_status if item and item.strip()}
    capabilities_state = state.setdefault("capabilities", {})
    pending_caps: list[dict[str, Any]] = []
    honor_existing_entries = args.resume or seeded_count > 0 or existing_state is not None

    for cap in raw_caps:
        capability_id = str(cap.get("id"))
        existing_entry = capabilities_state.get(capability_id)
        if honor_existing_entries and isinstance(existing_entry, dict):
            current_status = str(existing_entry.get("status") or "pending").lower()
            if current_status in {"stable"} and "stable" not in rerun_statuses:
                continue
            if current_status in {"unstable", "error", "skipped"} and current_status not in rerun_statuses:
                continue
        pending_caps.append(cap)

    if args.limit and args.limit > 0:
        pending_caps = pending_caps[: args.limit]

    casepacks = matrix._load_casepacks(args.casepack_file)
    registry = matrix.BindingRegistry(repo_root=matrix.ROOT, host_root=matrix.ROOT)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    args.state_file.parent.mkdir(parents=True, exist_ok=True)
    args.matrix_file.parent.mkdir(parents=True, exist_ok=True)

    _json_dump(args.state_file, state)
    snapshot = _write_matrix_snapshot(state=state, matrix_file=args.matrix_file)

    for cap in pending_caps:
        capability_id = str(cap.get("id"))
        try:
            report = matrix._run_for_capability(
                raw_capability=cap,
                casepacks=casepacks,
                registry=registry,
                allow_remote_openapi=args.allow_remote_openapi,
                semantic_strict=args.semantic_strict,
                semantic_min_pass_rate=args.semantic_min_pass_rate,
                require_semantic_casepack=args.require_semantic_casepack,
            )
            report_path = args.out_dir / f"{matrix._safe_slug(capability_id)}.json"
            _json_dump(report_path, report)
            capabilities_state[capability_id] = _entry_from_report(report, report_path)
        except Exception as exc:
            capabilities_state[capability_id] = _entry_from_exception(exc)
            state["updated_at"] = _iso_now()
            _json_dump(args.state_file, state)
            snapshot = _write_matrix_snapshot(state=state, matrix_file=args.matrix_file)
            print(f"[error] {capability_id}: {type(exc).__name__}: {exc}")
            if args.stop_on_error:
                raise SystemExit(2)
            continue

        state["updated_at"] = _iso_now()
        _json_dump(args.state_file, state)
        snapshot = _write_matrix_snapshot(state=state, matrix_file=args.matrix_file)
        status = capabilities_state[capability_id].get("status")
        print(
            f"[done] {capability_id}: {status} | "
            f"stable={snapshot['summary']['stable']} unstable={snapshot['summary']['unstable']} "
            f"error={snapshot['summary']['error']} pending={snapshot['summary']['pending']}"
        )

    summary = snapshot["summary"]
    print("Incremental cognitive stability snapshot updated")
    print(f"  state: {_safe_rel(args.state_file)}")
    print(f"  matrix: {_safe_rel(args.matrix_file)}")
    print(f"  reports: {_safe_rel(args.out_dir)}")
    print(f"  seeded_from_existing: {seeded_count}")
    print(f"  stable: {summary['stable']}")
    print(f"  unstable: {summary['unstable']}")
    print(f"  error: {summary['error']}")
    print(f"  pending: {summary['pending']}")

    if summary["error"] > 0:
        return 2
    if summary["unstable"] > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

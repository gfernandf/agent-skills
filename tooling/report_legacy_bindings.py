#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
LEGACY_ROOT = ROOT / "bindings" / "legacy_missing_capability"
OFFICIAL_ROOT = ROOT / "bindings" / "official"
DEFAULT_REPORT = ROOT / "artifacts" / "legacy_bindings_report.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Report legacy bindings and candidate canonical replacements."
    )
    parser.add_argument(
        "--report-file",
        type=Path,
        default=DEFAULT_REPORT,
        help="Path for JSON report output.",
    )
    return parser.parse_args()


def _candidate_capability_dirs(capability_dir: str) -> list[str]:
    candidates: list[str] = []

    prefix_aliases = {
        "text.content.": "reasoning.content.",
        "eval.": "evaluation.",
        "ops.trace.": "evidence.trace.",
    }
    for old_prefix, new_prefix in prefix_aliases.items():
        if capability_dir.startswith(old_prefix):
            candidates.append(new_prefix + capability_dir[len(old_prefix) :])

    explicit_aliases = {
        "agent.task.plan": "reasoning.plan.generate",
        "agent.plan.split": "reasoning.plan.decompose",
        "agent.plan.run": "agent.plan.execute",
    }
    mapped = explicit_aliases.get(capability_dir)
    if mapped:
        candidates.append(mapped)

    return list(dict.fromkeys(candidates))


def main() -> int:
    args = parse_args()
    args.report_file.parent.mkdir(parents=True, exist_ok=True)

    if not LEGACY_ROOT.is_dir():
        payload = {
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "status": "no_legacy_directory",
            "legacy_root": str(LEGACY_ROOT),
            "items": [],
            "summary": {
                "capability_dirs": 0,
                "binding_files": 0,
                "with_candidate_replacement": 0,
            },
        }
        args.report_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"No legacy directory found. Report written: {args.report_file}")
        return 0

    items: list[dict[str, object]] = []
    total_files = 0
    with_candidate = 0

    for capability_path in sorted(LEGACY_ROOT.iterdir()):
        if not capability_path.is_dir():
            continue

        capability_id = capability_path.name
        legacy_files = sorted(
            [p.name for p in capability_path.glob("*.yaml") if p.is_file()]
        )
        total_files += len(legacy_files)

        candidate_dirs: list[dict[str, object]] = []
        for candidate in _candidate_capability_dirs(capability_id):
            candidate_path = OFFICIAL_ROOT / candidate
            files = sorted(
                [p.name for p in candidate_path.glob("*.yaml") if p.is_file()]
            )
            if files:
                with_candidate += 1
                candidate_dirs.append(
                    {
                        "capability_id": candidate,
                        "official_binding_files": files,
                    }
                )

        items.append(
            {
                "legacy_capability_id": capability_id,
                "legacy_binding_files": legacy_files,
                "candidate_replacements": candidate_dirs,
            }
        )

    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "status": "ok",
        "legacy_root": str(LEGACY_ROOT),
        "official_root": str(OFFICIAL_ROOT),
        "items": items,
        "summary": {
            "capability_dirs": len(items),
            "binding_files": total_files,
            "with_candidate_replacement": with_candidate,
        },
    }

    args.report_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Legacy bindings report written: {args.report_file}")
    print(
        "Summary: "
        f"dirs={payload['summary']['capability_dirs']} "
        f"files={payload['summary']['binding_files']} "
        f"with_candidate_replacement={payload['summary']['with_candidate_replacement']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

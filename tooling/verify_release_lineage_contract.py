#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LINEAGE_FILE = ROOT / "artifacts" / "release_lineage.json"
DEFAULT_REPORT_FILE = ROOT / "artifacts" / "release_lineage_contract_report.json"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify release lineage contract shape and provenance integrity."
    )
    parser.add_argument(
        "--lineage-file",
        type=Path,
        default=DEFAULT_LINEAGE_FILE,
        help="Path to release lineage JSON artifact.",
    )
    parser.add_argument(
        "--report-file",
        type=Path,
        default=DEFAULT_REPORT_FILE,
        help="Path to write verification report JSON.",
    )
    parser.add_argument(
        "--allow-failed-lineage-status",
        action="store_true",
        help="Allow lineage status=failed without failing this verifier.",
    )
    return parser.parse_args()


def _append_check(
    checks: list[dict[str, Any]],
    *,
    check_id: str,
    passed: bool,
    detail: str,
) -> None:
    checks.append(
        {
            "check_id": check_id,
            "passed": passed,
            "detail": detail,
        }
    )


def _load_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not path.exists():
        return None, "missing"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return None, f"invalid_json: {exc}"
    if not isinstance(payload, dict):
        return None, "invalid_shape"
    return payload, None


def main() -> int:
    args = _parse_args()
    args.report_file.parent.mkdir(parents=True, exist_ok=True)

    checks: list[dict[str, Any]] = []

    data, error = _load_json(args.lineage_file)
    if error is not None or data is None:
        _append_check(
            checks,
            check_id="lineage_file_present",
            passed=False,
            detail=f"lineage_file={args.lineage_file}; error={error}",
        )
    else:
        _append_check(
            checks,
            check_id="lineage_file_present",
            passed=True,
            detail=f"lineage_file={args.lineage_file}",
        )

        contract = data.get("contract")
        _append_check(
            checks,
            check_id="lineage_contract_expected",
            passed=contract == "release_lineage_v1",
            detail=f"contract={contract}",
        )

        provenance = data.get("provenance")
        _append_check(
            checks,
            check_id="lineage_provenance_present",
            passed=isinstance(provenance, dict),
            detail="present" if isinstance(provenance, dict) else "missing_or_invalid",
        )

        schema_version = (
            provenance.get("schema_version") if isinstance(provenance, dict) else None
        )
        _append_check(
            checks,
            check_id="lineage_schema_version_expected",
            passed=schema_version == "1.1",
            detail=f"schema_version={schema_version}",
        )

        status = str(data.get("status", "unknown")).strip().lower()
        status_ok = status == "passed" or (
            args.allow_failed_lineage_status and status == "failed"
        )
        _append_check(
            checks,
            check_id="lineage_status_allowed",
            passed=status_ok,
            detail=f"status={status}",
        )

        summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
        total_checks = int(summary.get("total_checks") or 0)
        passed_checks = int(summary.get("passed_checks") or 0)
        failed_checks = int(summary.get("failed_checks") or 0)
        _append_check(
            checks,
            check_id="summary_consistent",
            passed=(passed_checks + failed_checks) == total_checks,
            detail=(
                f"total_checks={total_checks}; passed_checks={passed_checks}; "
                f"failed_checks={failed_checks}"
            ),
        )

        lineage = data.get("lineage") if isinstance(data.get("lineage"), dict) else {}
        nodes = lineage.get("nodes") if isinstance(lineage.get("nodes"), list) else []
        edges = lineage.get("edges") if isinstance(lineage.get("edges"), list) else []
        _append_check(
            checks,
            check_id="lineage_nodes_nonempty",
            passed=len(nodes) > 0,
            detail=f"nodes={len(nodes)}",
        )
        _append_check(
            checks,
            check_id="lineage_edges_nonempty",
            passed=len(edges) > 0,
            detail=f"edges={len(edges)}",
        )

        node_ids = {str(node.get("id", "")) for node in nodes if isinstance(node, dict)}
        node_types = {
            str(node.get("type", "")).strip()
            for node in nodes
            if isinstance(node, dict)
        }
        missing_types = sorted({"source", "job", "artifact", "decision"} - node_types)
        _append_check(
            checks,
            check_id="lineage_required_node_types_present",
            passed=not missing_types,
            detail="present" if not missing_types else f"missing={missing_types}",
        )

        missing_refs: list[str] = []
        for edge in edges:
            if not isinstance(edge, dict):
                missing_refs.append("edge:not_object")
                continue
            source = str(edge.get("source", ""))
            target = str(edge.get("target", ""))
            if source not in node_ids:
                missing_refs.append(f"source:{source}")
            if target not in node_ids:
                missing_refs.append(f"target:{target}")
        _append_check(
            checks,
            check_id="lineage_edges_reference_nodes",
            passed=not missing_refs,
            detail="ok" if not missing_refs else f"missing_refs={missing_refs[:10]}",
        )

        completeness_checks = (
            data.get("completeness_checks")
            if isinstance(data.get("completeness_checks"), list)
            else []
        )
        completeness_failed = [
            item
            for item in completeness_checks
            if isinstance(item, dict) and not bool(item.get("passed"))
        ]
        _append_check(
            checks,
            check_id="lineage_completeness_checks_all_passed",
            passed=len(completeness_failed) == 0,
            detail=f"failed_checks={len(completeness_failed)}",
        )

    passed = sum(1 for item in checks if item.get("passed"))
    total = len(checks)
    failed = total - passed

    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "status": "passed" if failed == 0 else "failed",
        "contract": "release_lineage_contract_v1",
        "summary": {
            "total_checks": total,
            "passed_checks": passed,
            "failed_checks": failed,
        },
        "checks": checks,
        "inputs": {
            "lineage_file": str(args.lineage_file),
            "allow_failed_lineage_status": args.allow_failed_lineage_status,
        },
    }

    args.report_file.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("Release lineage contract verification")
    print(f"- status: {report['status']}")
    print(f"- checks: {passed}/{total}")
    print(f"- report: {args.report_file}")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

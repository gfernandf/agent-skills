#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
REQUIRED_CHECKS_FILE = ROOT / "docs" / "required_status_checks.json"
BRANCH_POLICY_FILE = ROOT / "docs" / "BRANCH_PROTECTION_POLICY.md"
WORKFLOWS = {
    "ci.yml": ROOT / ".github" / "workflows" / "ci.yml",
    "smoke.yml": ROOT / ".github" / "workflows" / "smoke.yml",
}
DEFAULT_REPORT = ROOT / "artifacts" / "required_status_checks_consistency_report.json"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify consistency of required status checks across docs and workflows."
    )
    parser.add_argument(
        "--report-file",
        type=Path,
        default=DEFAULT_REPORT,
        help="Path to write JSON report.",
    )
    return parser.parse_args()


def _check(condition: bool, check_id: str, detail: str) -> dict[str, object]:
    return {"check_id": check_id, "passed": condition, "detail": detail}


def main() -> int:
    args = _parse_args()
    args.report_file.parent.mkdir(parents=True, exist_ok=True)

    checks: list[dict[str, object]] = []

    checks.append(
        _check(
            REQUIRED_CHECKS_FILE.exists(),
            "required_checks_file_exists",
            str(REQUIRED_CHECKS_FILE),
        )
    )
    checks.append(
        _check(
            BRANCH_POLICY_FILE.exists(),
            "branch_policy_file_exists",
            str(BRANCH_POLICY_FILE),
        )
    )

    data: dict[str, object] = {}
    if REQUIRED_CHECKS_FILE.exists():
        try:
            data = json.loads(REQUIRED_CHECKS_FILE.read_text(encoding="utf-8"))
            checks.append(_check(True, "required_checks_file_json_valid", "valid json"))
        except Exception as exc:
            checks.append(
                _check(False, "required_checks_file_json_valid", f"invalid json: {exc}")
            )

    required_checks = (
        data.get("required_status_checks", [])
        if isinstance(data.get("required_status_checks"), list)
        else []
    )
    mapping = (
        data.get("check_job_mapping", {})
        if isinstance(data.get("check_job_mapping"), dict)
        else {}
    )
    policy_text = (
        BRANCH_POLICY_FILE.read_text(encoding="utf-8")
        if BRANCH_POLICY_FILE.exists()
        else ""
    )

    checks.append(
        _check(
            bool(required_checks),
            "required_checks_non_empty",
            f"count={len(required_checks)}",
        )
    )

    for check_name in required_checks:
        if not isinstance(check_name, str):
            checks.append(_check(False, "required_check_name_type", str(check_name)))
            continue

        checks.append(
            _check(
                check_name in policy_text,
                f"policy_doc_mentions_required_check:{check_name}",
                check_name,
            )
        )

        entry = mapping.get(check_name)
        checks.append(
            _check(
                isinstance(entry, dict),
                f"mapping_entry_present:{check_name}",
                str(entry),
            )
        )
        if not isinstance(entry, dict):
            continue

        workflow_name = entry.get("workflow")
        job_id = entry.get("job_id")
        workflow_path = (
            WORKFLOWS.get(workflow_name) if isinstance(workflow_name, str) else None
        )

        checks.append(
            _check(
                isinstance(workflow_path, Path) and workflow_path.exists(),
                f"workflow_exists_for_required_check:{check_name}",
                str(workflow_name),
            )
        )

        if (
            isinstance(workflow_path, Path)
            and workflow_path.exists()
            and isinstance(job_id, str)
        ):
            content = workflow_path.read_text(encoding="utf-8")
            checks.append(
                _check(
                    f"{job_id}:" in content,
                    f"workflow_job_id_present:{check_name}",
                    f"{workflow_name}:{job_id}",
                )
            )
        else:
            checks.append(
                _check(
                    False,
                    f"workflow_job_id_present:{check_name}",
                    f"{workflow_name}:{job_id}",
                )
            )

    passed = sum(1 for c in checks if c.get("passed") is True)
    total = len(checks)
    failed = total - passed
    pass_ratio = (passed / total) if total else 0.0

    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "status": "passed" if failed == 0 else "failed",
        "contract": "required_status_checks_consistency_v1",
        "summary": {
            "total": total,
            "passed": passed,
            "failed": failed,
            "pass_ratio": pass_ratio,
        },
        "checks": checks,
    }

    args.report_file.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("Required status checks consistency summary")
    print(f"- passed: {passed}/{total}")
    print(f"- pass_ratio: {pass_ratio:.3f}")
    print(f"- report: {args.report_file}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

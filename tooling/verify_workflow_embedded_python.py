#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import textwrap
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
WORKFLOW_FILES = (
    ROOT / ".github" / "workflows" / "ci.yml",
    ROOT / ".github" / "workflows" / "smoke.yml",
)
DEFAULT_REPORT = ROOT / "artifacts" / "workflow_embedded_python_report.json"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Verify syntax of embedded Python heredoc blocks in workflow YAML files."
        )
    )
    parser.add_argument(
        "--report-file",
        type=Path,
        default=DEFAULT_REPORT,
        help="Path to write JSON report.",
    )
    return parser.parse_args()


def _extract_python_blocks(text: str) -> list[tuple[int, str]]:
    lines = text.splitlines()
    blocks: list[tuple[int, str]] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if "python - << 'PY'" in line:
            start_line = i + 2
            i += 1
            collected: list[str] = []
            while i < len(lines) and lines[i].strip() != "PY":
                collected.append(lines[i])
                i += 1
            code = textwrap.dedent("\n".join(collected)).strip("\n")
            blocks.append((start_line, code))
        i += 1
    return blocks


def main() -> int:
    args = _parse_args()
    args.report_file.parent.mkdir(parents=True, exist_ok=True)

    checks: list[dict[str, object]] = []

    for workflow_path in WORKFLOW_FILES:
        exists = workflow_path.exists()
        checks.append(
            {
                "check_id": f"workflow_exists:{workflow_path.name}",
                "passed": exists,
                "detail": str(workflow_path),
            }
        )
        if not exists:
            continue

        text = workflow_path.read_text(encoding="utf-8")
        blocks = _extract_python_blocks(text)
        checks.append(
            {
                "check_id": f"workflow_python_blocks_found:{workflow_path.name}",
                "passed": True,
                "detail": f"count={len(blocks)}",
            }
        )

        for idx, (start_line, code) in enumerate(blocks, start=1):
            check_id = f"workflow_python_syntax:{workflow_path.name}:block_{idx}:line_{start_line}"
            try:
                compile(code, f"{workflow_path.name}:block_{idx}", "exec")
            except SyntaxError as exc:
                detail = f"syntax error at line {exc.lineno}: {exc.msg}"
                checks.append(
                    {
                        "check_id": check_id,
                        "passed": False,
                        "detail": detail,
                    }
                )
            else:
                checks.append(
                    {
                        "check_id": check_id,
                        "passed": True,
                        "detail": "ok",
                    }
                )

    passed = sum(1 for c in checks if c.get("passed") is True)
    total = len(checks)
    failed = total - passed
    pass_ratio = (passed / total) if total else 0.0

    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "status": "passed" if failed == 0 else "failed",
        "contract": "workflow_embedded_python_v1",
        "summary": {
            "total": total,
            "passed": passed,
            "failed": failed,
            "pass_ratio": pass_ratio,
        },
        "checks": checks,
    }

    args.report_file.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("Workflow embedded Python summary")
    print(f"- passed: {passed}/{total}")
    print(f"- pass_ratio: {pass_ratio:.3f}")
    print(f"- report: {args.report_file}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

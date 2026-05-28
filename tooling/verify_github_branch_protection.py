#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
REQUIRED_CHECKS_FILE = ROOT / "docs" / "required_status_checks.json"
DEFAULT_REPORT = ROOT / "artifacts" / "github_branch_protection_report.json"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify GitHub branch protection settings via REST API."
    )
    parser.add_argument(
        "--report-file",
        type=Path,
        default=DEFAULT_REPORT,
        help="Path to write JSON report.",
    )
    parser.add_argument(
        "--repository",
        default=os.getenv("GITHUB_REPOSITORY", ""),
        help="Repository in owner/name format. Defaults to GITHUB_REPOSITORY.",
    )
    parser.add_argument(
        "--branches",
        default="main,master",
        help="Comma-separated branch names to inspect.",
    )
    parser.add_argument(
        "--fail-on-unverified",
        action="store_true",
        help="Fail if branch protection cannot be verified due to missing permissions/token.",
    )
    return parser.parse_args()


def _load_required_checks() -> list[str]:
    if not REQUIRED_CHECKS_FILE.exists():
        return []
    data = json.loads(REQUIRED_CHECKS_FILE.read_text(encoding="utf-8"))
    checks = data.get("required_status_checks", [])
    return [c for c in checks if isinstance(c, str)] if isinstance(checks, list) else []


def _api_get(url: str, token: str) -> tuple[int, dict[str, object] | None, str]:
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "agent-skills-branch-protection-verifier",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8")
            data = json.loads(raw) if raw else {}
            return resp.status, data if isinstance(data, dict) else {}, ""
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        return int(exc.code), None, detail
    except Exception as exc:
        return 0, None, str(exc)


def main() -> int:
    args = _parse_args()
    args.report_file.parent.mkdir(parents=True, exist_ok=True)

    token = os.getenv("GITHUB_TOKEN", "")
    required_checks = _load_required_checks()
    branches = [b.strip() for b in args.branches.split(",") if b.strip()]

    checks: list[dict[str, object]] = []
    unverified = False

    checks.append({"check_id": "repository_provided", "passed": bool(args.repository), "detail": args.repository})
    checks.append({"check_id": "github_token_present", "passed": bool(token), "detail": "present" if token else "missing"})

    if not args.repository or not token:
        unverified = True
    else:
        for branch in branches:
            url = f"https://api.github.com/repos/{args.repository}/branches/{branch}/protection"
            status, payload, detail = _api_get(url, token)
            checks.append(
                {
                    "check_id": f"branch_protection_api_call:{branch}",
                    "passed": status == 200,
                    "detail": f"status={status} {detail[:200]}",
                }
            )
            if status != 200 or payload is None:
                unverified = True
                continue

            required_status_checks = payload.get("required_status_checks")
            contexts = []
            if isinstance(required_status_checks, dict):
                raw_contexts = required_status_checks.get("contexts")
                if isinstance(raw_contexts, list):
                    contexts = [c for c in raw_contexts if isinstance(c, str)]

            for check_name in required_checks:
                checks.append(
                    {
                        "check_id": f"required_check_present:{branch}:{check_name}",
                        "passed": check_name in contexts,
                        "detail": check_name,
                    }
                )

            required_pr_reviews = payload.get("required_pull_request_reviews")
            checks.append(
                {
                    "check_id": f"require_pr_reviews:{branch}",
                    "passed": isinstance(required_pr_reviews, dict),
                    "detail": "configured" if isinstance(required_pr_reviews, dict) else "missing",
                }
            )

    passed = sum(1 for c in checks if c.get("passed") is True)
    total = len(checks)
    failed = total - passed
    pass_ratio = (passed / total) if total else 0.0

    status = "passed" if failed == 0 else "failed"
    if unverified and not args.fail_on_unverified:
        status = "unverified"

    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "status": status,
        "contract": "github_branch_protection_v1",
        "summary": {
            "total": total,
            "passed": passed,
            "failed": failed,
            "pass_ratio": pass_ratio,
            "unverified": unverified,
        },
        "repository": args.repository,
        "branches": branches,
        "required_checks": required_checks,
        "checks": checks,
    }

    args.report_file.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("GitHub branch protection summary")
    print(f"- status: {status}")
    print(f"- passed: {passed}/{total}")
    print(f"- report: {args.report_file}")

    if status == "failed":
        return 1
    if status == "unverified" and args.fail_on_unverified:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

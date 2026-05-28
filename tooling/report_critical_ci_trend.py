#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REPORT = ROOT / "artifacts" / "critical_ci_trend_report.json"

CRITICAL_JOBS = [
    "smoke",
    "runtime_canary",
    "dx_metrics",
    "policy-bundle-governance",
]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Report stability trend of critical CI jobs from GitHub Actions API."
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
        help="Repository owner/name. Defaults to GITHUB_REPOSITORY.",
    )
    parser.add_argument(
        "--window",
        type=int,
        default=20,
        help="How many recent workflow runs to inspect per workflow.",
    )
    return parser.parse_args()


def _api_get(url: str, token: str) -> tuple[int, dict[str, object] | None, str]:
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "agent-skills-ci-trend",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            raw = resp.read().decode("utf-8")
            data = json.loads(raw) if raw else {}
            return resp.status, data if isinstance(data, dict) else {}, ""
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        return int(exc.code), None, detail
    except Exception as exc:
        return 0, None, str(exc)


def _collect_runs(repo: str, token: str, workflow_file: str, window: int) -> list[dict[str, object]]:
    q = urllib.parse.urlencode({"per_page": str(window), "status": "completed"})
    url = f"https://api.github.com/repos/{repo}/actions/workflows/{workflow_file}/runs?{q}"
    status, payload, _ = _api_get(url, token)
    if status != 200 or payload is None:
        return []
    runs = payload.get("workflow_runs")
    return [r for r in runs if isinstance(r, dict)] if isinstance(runs, list) else []


def _collect_jobs_for_run(repo: str, token: str, run_id: int) -> list[dict[str, object]]:
    url = f"https://api.github.com/repos/{repo}/actions/runs/{run_id}/jobs?per_page=100"
    status, payload, _ = _api_get(url, token)
    if status != 200 or payload is None:
        return []
    jobs = payload.get("jobs")
    return [j for j in jobs if isinstance(j, dict)] if isinstance(jobs, list) else []


def main() -> int:
    args = _parse_args()
    args.report_file.parent.mkdir(parents=True, exist_ok=True)

    token = os.getenv("GITHUB_TOKEN", "")
    repo = args.repository

    trend: dict[str, dict[str, object]] = {
        name: {
            "samples": 0,
            "passed": 0,
            "failed": 0,
            "other": 0,
            "pass_rate": 0.0,
            "recent": [],
        }
        for name in CRITICAL_JOBS
    }

    notes: list[str] = []
    status = "passed"

    if not repo or not token:
        status = "unverified"
        if not repo:
            notes.append("GITHUB_REPOSITORY is missing")
        if not token:
            notes.append("GITHUB_TOKEN is missing")
    else:
        workflow_files = ["smoke.yml", "ci.yml"]
        for workflow_file in workflow_files:
            runs = _collect_runs(repo, token, workflow_file, args.window)
            for run in runs:
                run_id = run.get("id")
                if not isinstance(run_id, int):
                    continue
                jobs = _collect_jobs_for_run(repo, token, run_id)
                for job in jobs:
                    name = job.get("name")
                    if not isinstance(name, str) or name not in trend:
                        continue
                    conclusion = str(job.get("conclusion", "unknown")).lower()
                    item = trend[name]
                    item["samples"] = int(item["samples"]) + 1
                    if conclusion == "success":
                        item["passed"] = int(item["passed"]) + 1
                    elif conclusion in {"failure", "timed_out", "cancelled", "startup_failure"}:
                        item["failed"] = int(item["failed"]) + 1
                    else:
                        item["other"] = int(item["other"]) + 1
                    recent = item["recent"]
                    if isinstance(recent, list) and len(recent) < 8:
                        recent.append(
                            {
                                "run_id": run_id,
                                "conclusion": conclusion,
                                "completed_at": run.get("updated_at"),
                                "workflow": workflow_file,
                            }
                        )

        for _, data in trend.items():
            samples = int(data["samples"])
            passed = int(data["passed"])
            data["pass_rate"] = (passed / samples) if samples else 0.0

    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "status": status,
        "contract": "critical_ci_trend_v1",
        "repository": repo,
        "window": args.window,
        "critical_jobs": trend,
        "notes": notes,
    }

    args.report_file.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("Critical CI trend summary")
    print(f"- status: {status}")
    print(f"- report: {args.report_file}")
    for name in CRITICAL_JOBS:
        d = trend[name]
        print(f"- {name}: {d['passed']}/{d['samples']} pass_rate={d['pass_rate']:.3f}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3

from __future__ import annotations

import json
import subprocess
import urllib.request
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPORT_FILE = ROOT / "artifacts" / "governance_tenancy_rollout_report.json"


@dataclass
class RepoGate:
    repo: str
    workflow_name: str
    workflow_path: str
    branch: str


GATES = [
    RepoGate(
        repo="gfernandf/agent-skills",
        workflow_name="CI \u2014 Test \u00b7 Lint \u00b7 Type-check \u00b7 Security",
        workflow_path=".github/workflows/ci.yml",
        branch="master",
    ),
    RepoGate(
        repo="gfernandf/agent-skill-registry",
        workflow_name="Validate Registry",
        workflow_path=".github/workflows/validate.yml",
        branch="main",
    ),
]


def _latest_workflow_run(gate: RepoGate, expected_head: str) -> dict:
    url = (
        "https://api.github.com/repos/"
        f"{gate.repo}/actions/runs?branch={gate.branch}&per_page=50"
    )
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "copilot-agent",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))

    runs = payload.get("workflow_runs", [])
    if not isinstance(runs, list):
        return {}

    by_path = [run for run in runs if run.get("path") == gate.workflow_path]
    if by_path:
        matching_head = [
            run
            for run in by_path
            if isinstance(run.get("head_sha"), str)
            and expected_head.startswith(run.get("head_sha"))
        ]
        if matching_head:
            return matching_head[0]
        return by_path[0]

    # Fallback for older workflow runs that may not expose path consistently.
    for run in runs:
        if run.get("name") == gate.workflow_name:
            return run
    return {}


def _read_next_capability() -> str:
    if not REPORT_FILE.exists():
        return "unknown (missing governance_tenancy_rollout_report.json)"

    try:
        report = json.loads(REPORT_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return "unknown (invalid governance_tenancy_rollout_report.json)"

    cohort = report.get("recommended_next_cohort")
    if isinstance(cohort, list) and cohort:
        first = cohort[0]
        return first if isinstance(first, str) else "unknown (invalid cohort entry)"

    return "none"


def _git_head(path: Path) -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=path,
        text=True,
        capture_output=True,
        check=True,
    )
    return proc.stdout.strip()


def main() -> int:
    skills_head = _git_head(ROOT)
    registry_head = _git_head(ROOT.parent / "agent-skill-registry")
    expected_heads = {
        "gfernandf/agent-skills": skills_head,
        "gfernandf/agent-skill-registry": registry_head,
    }

    all_green = True
    print("Governance autopilot gate")
    print("- Local heads:")
    print(f"  * agent-skills: {skills_head}")
    print(f"  * agent-skill-registry: {registry_head}")

    for gate in GATES:
        expected = expected_heads[gate.repo]
        run = _latest_workflow_run(gate, expected)
        if not run:
            print(f"- {gate.repo}: workflow not found ({gate.workflow_name})")
            all_green = False
            continue

        status = run.get("status")
        conclusion = run.get("conclusion")
        head_sha = run.get("head_sha")
        run_id = run.get("id")
        html_url = run.get("html_url")
        current_head_ok = isinstance(head_sha, str) and expected.startswith(head_sha)
        completed_ok = status == "completed" and conclusion == "success"
        gate_ok = current_head_ok and completed_ok
        all_green = all_green and gate_ok

        print(f"- {gate.repo}")
        print(f"  * run_id: {run_id}")
        print(f"  * status: {status}")
        print(f"  * conclusion: {conclusion}")
        print(f"  * run head: {head_sha}")
        print(f"  * local head: {expected}")
        print(f"  * head_match: {current_head_ok}")
        print(f"  * gate_ok: {gate_ok}")
        print(f"  * url: {html_url}")

    next_capability = _read_next_capability()
    print(f"- next_capability: {next_capability}")

    if all_green:
        print("- decision: advance")
        return 0

    print("- decision: wait")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

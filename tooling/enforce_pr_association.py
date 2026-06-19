#!/usr/bin/env python3
"""Fail CI when a protected-branch push commit has no associated pull request.

This helps enforce "changes through PR" even when branch protection bypass is possible.
The script is intentionally no-op outside push events or outside protected branches.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request


PROTECTED_REFS = {"refs/heads/main", "refs/heads/master"}


def _env(name: str, default: str = "") -> str:
    return str(os.environ.get(name, default)).strip()


def _fetch_associated_prs(repo: str, sha: str, token: str) -> list[dict]:
    url = f"https://api.github.com/repos/{repo}/commits/{sha}/pulls"
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "orca-pr-enforcement",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        body = resp.read().decode("utf-8", errors="replace")
    payload = json.loads(body)
    return payload if isinstance(payload, list) else []


def main() -> int:
    event_name = _env("GITHUB_EVENT_NAME")
    ref = _env("GITHUB_REF")
    repo = _env("GITHUB_REPOSITORY")
    sha = _env("GITHUB_SHA")
    token = _env("GITHUB_TOKEN")

    if event_name != "push":
        print(f"[enforce-pr] skip: event={event_name}")
        return 0
    if ref not in PROTECTED_REFS:
        print(f"[enforce-pr] skip: ref={ref}")
        return 0

    if not (repo and sha and token):
        print("[enforce-pr] ERROR: missing required GitHub context/token env vars")
        return 1

    try:
        prs = _fetch_associated_prs(repo, sha, token)
    except urllib.error.HTTPError as exc:
        print(f"[enforce-pr] ERROR: GitHub API HTTP {exc.code}: {exc.reason}")
        return 1
    except Exception as exc:
        print(f"[enforce-pr] ERROR: unable to query associated PRs: {exc}")
        return 1

    if prs:
        numbers = ", ".join(str(p.get("number")) for p in prs if p.get("number"))
        print(f"[enforce-pr] OK: commit has associated PR(s): {numbers}")
        return 0

    print(
        "[enforce-pr] FAIL: direct push to protected branch without associated PR. "
        "Use a pull request with required checks."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3

from __future__ import annotations

import argparse
import fnmatch
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
        default="master",
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


def _api_get(url: str, token: str) -> tuple[int, object | None, str]:
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
            return resp.status, data, ""
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        return int(exc.code), None, detail
    except Exception as exc:
        return 0, None, str(exc)


def _api_get_list(
    url: str, token: str
) -> tuple[int, list[dict[str, object]] | None, str]:
    status, payload, detail = _api_get(url, token)
    if status != 200 or not isinstance(payload, list):
        return status, None, detail
    return status, [item for item in payload if isinstance(item, dict)], detail


def _api_get_dict(url: str, token: str) -> tuple[int, dict[str, object] | None, str]:
    status, payload, detail = _api_get(url, token)
    if status != 200 or not isinstance(payload, dict):
        return status, None, detail
    return status, payload, detail


def _split_repository(repository: str) -> tuple[str, str] | None:
    if "/" not in repository:
        return None
    owner, repo = repository.split("/", 1)
    if not owner or not repo:
        return None
    return owner, repo


def _get_default_branch(repository: str, token: str) -> str | None:
    repo_split = _split_repository(repository)
    if repo_split is None:
        return None
    owner, repo = repo_split
    url = f"https://api.github.com/repos/{owner}/{repo}"
    status, payload, _ = _api_get_dict(url, token)
    if status != 200 or payload is None:
        return None
    value = payload.get("default_branch")
    return value if isinstance(value, str) and value else None


def _matches_ref_name(
    branch: str, include: list[str], exclude: list[str], default_branch: str | None
) -> bool:
    ref = f"refs/heads/{branch}"

    if include:
        include_match = False
        for pattern in include:
            if pattern == "~ALL":
                include_match = True
                break
            if pattern == "~DEFAULT_BRANCH":
                include_match = default_branch is not None and branch == default_branch
                break
            if fnmatch.fnmatch(ref, pattern) or fnmatch.fnmatch(branch, pattern):
                include_match = True
                break
        if not include_match:
            return False

    for pattern in exclude:
        if pattern == "~ALL":
            return False
        if pattern == "~DEFAULT_BRANCH":
            if default_branch is not None and branch == default_branch:
                return False
            continue
        if fnmatch.fnmatch(ref, pattern) or fnmatch.fnmatch(branch, pattern):
            return False

    return True


def _rules_from_matching_rulesets(
    repository: str, branch: str, token: str, default_branch: str | None
) -> tuple[int, list[dict[str, object]] | None, str]:
    repo_split = _split_repository(repository)
    if repo_split is None:
        return 0, None, "invalid repository format"
    owner, repo = repo_split

    list_url = (
        f"https://api.github.com/repos/{owner}/{repo}/rulesets"
        "?includes_parents=true&targets=branch&per_page=100"
    )
    status, ruleset_refs, detail = _api_get_list(list_url, token)
    if status != 200 or ruleset_refs is None:
        return status, None, detail

    aggregated_rules: list[dict[str, object]] = []
    for ruleset_ref in ruleset_refs:
        ruleset_id = ruleset_ref.get("id")
        if not isinstance(ruleset_id, int):
            continue

        ruleset_url = (
            f"https://api.github.com/repos/{owner}/{repo}/rulesets/{ruleset_id}"
            "?includes_parents=true"
        )
        ruleset_status, ruleset_payload, ruleset_detail = _api_get_dict(
            ruleset_url, token
        )
        if ruleset_status != 200 or ruleset_payload is None:
            continue

        enforcement = ruleset_payload.get("enforcement")
        if not isinstance(enforcement, str) or enforcement.lower() not in {
            "active",
            "enabled",
        }:
            continue

        target = ruleset_payload.get("target")
        if isinstance(target, str) and target.lower() != "branch":
            continue

        include: list[str] = []
        exclude: list[str] = []
        conditions = ruleset_payload.get("conditions")
        if isinstance(conditions, dict):
            ref_name = conditions.get("ref_name")
            if isinstance(ref_name, dict):
                raw_include = ref_name.get("include")
                raw_exclude = ref_name.get("exclude")
                if isinstance(raw_include, list):
                    include = [v for v in raw_include if isinstance(v, str)]
                if isinstance(raw_exclude, list):
                    exclude = [v for v in raw_exclude if isinstance(v, str)]

        if not _matches_ref_name(branch, include, exclude, default_branch):
            continue

        raw_rules = ruleset_payload.get("rules")
        if isinstance(raw_rules, list):
            aggregated_rules.extend([r for r in raw_rules if isinstance(r, dict)])

    return 200, aggregated_rules, ""


def _iter_strings(value: object) -> list[str]:
    strings: list[str] = []
    if isinstance(value, str):
        strings.append(value)
    elif isinstance(value, dict):
        for nested in value.values():
            strings.extend(_iter_strings(nested))
    elif isinstance(value, list):
        for nested in value:
            strings.extend(_iter_strings(nested))
    return strings


def _rule_type(rule: dict[str, object]) -> str:
    value = rule.get("type")
    return value.lower() if isinstance(value, str) else ""


def _rule_mentions(rule: dict[str, object], needle: str) -> bool:
    needle_l = needle.lower()
    for text in _iter_strings(rule):
        text_l = text.lower()
        if text_l == needle_l or needle_l in text_l:
            return True
    return False


def _rule_has_required_pr_reviews(rule: dict[str, object]) -> bool:
    rule_type = _rule_type(rule)
    if "pull_request" not in rule_type and "review" not in rule_type:
        return False

    if "pull_request" in rule_type:
        parameters = rule.get("parameters")
        if isinstance(parameters, dict):
            for key in (
                "required_approving_review_count",
                "approving_review_count",
            ):
                value = parameters.get(key)
                if isinstance(value, int) and value >= 1:
                    return True
        # Some ruleset APIs omit explicit counts but still enforce review gates.
        return True

    strings = _iter_strings(rule.get("parameters"))
    if "1" in strings or "true" in {s.lower() for s in strings}:
        return True

    parameters = rule.get("parameters")
    if isinstance(parameters, dict):
        for key in ("required_approving_review_count", "approving_review_count"):
            value = parameters.get(key)
            if isinstance(value, int) and value >= 1:
                return True
    return False


def _evaluate_rules_for_branch(
    rules: list[dict[str, object]], required_checks: list[str]
) -> tuple[list[dict[str, object]], bool, bool]:
    checks: list[dict[str, object]] = []
    found_required_pr_reviews = False
    found_required_checks: dict[str, bool] = {check: False for check in required_checks}

    for rule in rules:
        if _rule_has_required_pr_reviews(rule):
            found_required_pr_reviews = True

        rule_type = _rule_type(rule)
        if (
            "status" not in rule_type
            and "check" not in rule_type
            and "workflow" not in rule_type
        ):
            continue

        for check_name in required_checks:
            if found_required_checks[check_name]:
                continue
            if _rule_mentions(rule, check_name):
                found_required_checks[check_name] = True

    for check_name, passed in found_required_checks.items():
        checks.append(
            {
                "check_id": f"required_check_present:ruleset:{check_name}",
                "passed": passed,
                "detail": check_name,
            }
        )

    checks.append(
        {
            "check_id": "require_pr_reviews:ruleset",
            "passed": found_required_pr_reviews,
            "detail": "configured" if found_required_pr_reviews else "missing",
        }
    )
    return checks, found_required_pr_reviews, all(found_required_checks.values())


def main() -> int:
    args = _parse_args()
    args.report_file.parent.mkdir(parents=True, exist_ok=True)

    token = os.getenv("GITHUB_TOKEN", "")
    required_checks = _load_required_checks()
    branches = [b.strip() for b in args.branches.split(",") if b.strip()]

    checks: list[dict[str, object]] = []
    unverified = False

    checks.append(
        {
            "check_id": "repository_provided",
            "passed": bool(args.repository),
            "detail": args.repository,
        }
    )
    checks.append(
        {
            "check_id": "github_token_present",
            "passed": bool(token),
            "detail": "present" if token else "missing",
        }
    )

    if not args.repository or not token:
        unverified = True
    else:
        default_branch = _get_default_branch(args.repository, token)
        for branch in branches:
            rules_url = f"https://api.github.com/repos/{args.repository}/rules/branches/{branch}"
            status, payload, detail = _api_get_list(rules_url, token)
            checks.append(
                {
                    "check_id": f"branch_rules_api_call:{branch}",
                    "passed": status == 200,
                    "detail": f"status={status} {detail[:200]}",
                }
            )
            if status != 200 or payload is None:
                unverified = True
                continue

            rules_checks, found_pr_reviews, found_status_checks = (
                _evaluate_rules_for_branch(payload, required_checks)
            )
            if found_pr_reviews and found_status_checks:
                for item in rules_checks:
                    item["check_id"] = item["check_id"].replace("ruleset", branch)
                    checks.append(item)
                continue

            ruleset_status, ruleset_rules, ruleset_detail = (
                _rules_from_matching_rulesets(
                    args.repository, branch, token, default_branch
                )
            )
            checks.append(
                {
                    "check_id": f"repository_rulesets_api_call:{branch}",
                    "passed": ruleset_status == 200,
                    "detail": f"status={ruleset_status} {ruleset_detail[:200]}",
                }
            )
            if ruleset_status != 200 or ruleset_rules is None:
                unverified = True
                continue

            ruleset_checks, ruleset_found_pr_reviews, ruleset_found_status_checks = (
                _evaluate_rules_for_branch(ruleset_rules, required_checks)
            )
            for item in ruleset_checks:
                item["check_id"] = item["check_id"].replace(
                    "ruleset", f"{branch}:rulesets"
                )
                checks.append(item)

            if not ruleset_found_pr_reviews or not ruleset_found_status_checks:
                # Verification succeeded but required controls were not found.
                # Keep status as failed instead of unverified.
                pass

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

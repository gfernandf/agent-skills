#!/usr/bin/env python3
"""
verify_release_gate_policy.py

Verify that the release gate policy file is well-formed and hasn't drifted
from the expected schema. This prevents policy regressions during manual edits.

Usage:
    python tooling/verify_release_gate_policy.py --report-file artifacts/report.json
"""

import json
import sys
from pathlib import Path
import argparse


EXPECTED_PROFILES = {"strict", "transitional", "promotion"}
EXPECTED_PROFILE_FIELDS = {
    "allow_trend_unverified",
    "max_high_failures",
    "max_medium_failures",
}


def verify_release_gate_policy(policy_file):
    """
    Verify release gate policy schema and content.
    Returns (status, issues, policy_data).
    """
    issues = []

    try:
        policy_data = json.loads(policy_file.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return "failed", [f"Policy file not found: {policy_file}"], None
    except json.JSONDecodeError as e:
        return "failed", [f"Policy file JSON error: {e}"], None

    # Check top-level structure
    if "profiles" not in policy_data:
        issues.append("Missing top-level 'profiles' field")
        return "failed", issues, policy_data

    profiles = policy_data["profiles"]
    if not isinstance(profiles, dict):
        issues.append(f"'profiles' must be dict, got {type(profiles).__name__}")
        return "failed", issues, policy_data

    # Check for expected profile names
    present_profiles = set(profiles.keys())
    missing_profiles = EXPECTED_PROFILES - present_profiles
    extra_profiles = present_profiles - EXPECTED_PROFILES

    if missing_profiles:
        issues.append(f"Missing profiles: {', '.join(sorted(missing_profiles))}")

    if extra_profiles:
        issues.append(f"Unexpected profiles: {', '.join(sorted(extra_profiles))}")

    # Validate each profile schema
    for profile_name, profile_config in profiles.items():
        if not isinstance(profile_config, dict):
            issues.append(
                f"Profile '{profile_name}' must be dict, got {type(profile_config).__name__}"
            )
            continue

        # Check required fields
        present_fields = set(profile_config.keys())
        missing_fields = EXPECTED_PROFILE_FIELDS - present_fields

        if missing_fields:
            issues.append(
                f"Profile '{profile_name}' missing fields: {', '.join(sorted(missing_fields))}"
            )

        # Validate field types and ranges
        if "allow_trend_unverified" in profile_config:
            if not isinstance(profile_config["allow_trend_unverified"], bool):
                issues.append(
                    f"Profile '{profile_name}' field 'allow_trend_unverified' must be bool"
                )

        for field in ["max_high_failures", "max_medium_failures", "max_low_failures"]:
            if field in profile_config:
                val = profile_config[field]
                if not isinstance(val, int):
                    issues.append(
                        f"Profile '{profile_name}' field '{field}' must be int, got {type(val).__name__}"
                    )
                elif val < 0:
                    issues.append(f"Profile '{profile_name}' field '{field}' cannot be negative")

    status = "passed" if not issues else "failed"
    return status, issues, policy_data


def main():
    parser = argparse.ArgumentParser(
        description="Verify release gate policy configuration"
    )
    parser.add_argument(
        "--policy-file",
        default=".github/release_gate_policy.json",
        help="Path to release gate policy file (default: .github/release_gate_policy.json)",
    )
    parser.add_argument(
        "--report-file",
        default="artifacts/release_gate_policy_verification_report.json",
        help="Path to output JSON report",
    )

    args = parser.parse_args()
    policy_file = Path(args.policy_file)
    report_file = Path(args.report_file)

    # Ensure output directory exists
    report_file.parent.mkdir(parents=True, exist_ok=True)

    status, issues, policy_data = verify_release_gate_policy(policy_file)

    report = {
        "status": status,
        "policy_file": str(policy_file),
        "issues": issues,
        "profiles_present": sorted(policy_data.get("profiles", {}).keys())
        if policy_data
        else [],
    }

    report_file.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Policy verification: {status}")
    if issues:
        print("Issues found:")
        for issue in issues:
            print(f"  - {issue}")
    else:
        print("No issues found.")

    sys.exit(0 if status == "passed" else 1)


if __name__ == "__main__":
    main()

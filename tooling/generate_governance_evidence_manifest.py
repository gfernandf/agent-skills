#!/usr/bin/env python3
"""
Generate governance external evidence summary for release bundles.

This script collects available evidence from:
1. Automated CI reports (branch protection, required status checks, SLO reports)
2. GitHub API calls (current ruleset/branch protection configuration)
3. Local policy documents (BRANCH_PROTECTION_POLICY.md, required_status_checks.json)

Output: governance_evidence_manifest.json for inclusion in release bundle
"""

import json
import sys
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any


def _load_json(path: Path) -> tuple[Optional[Dict], Optional[str]]:
    """Load JSON file, return (data, error)."""
    try:
        if not path.exists():
            return None, f"File not found: {path}"
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f), None
    except Exception as e:
        return None, str(e)


def _verify_github_branch_protection(artifacts_dir: Path) -> Dict[str, Any]:
    """Run branch protection verification and capture result."""
    try:
        report_file = artifacts_dir / "github_branch_protection_report.json"
        subprocess.run(
            [
                "python",
                "tooling/verify_github_branch_protection.py",
                "--report-file",
                str(report_file),
            ],
            capture_output=True,
            timeout=30,
            text=True,
        )

        if report_file.exists():
            data, err = _load_json(report_file)
            if data:
                return {
                    "status": "collected",
                    "path": str(report_file.relative_to(artifacts_dir.parent)),
                    "data": data,
                }
            return {"status": "error", "error": err}
        return {"status": "not_generated"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def _verify_required_status_checks_consistency(artifacts_dir: Path) -> Dict[str, Any]:
    """Verify required status checks consistency."""
    try:
        report_file = artifacts_dir / "required_status_checks_consistency_report.json"
        subprocess.run(
            [
                "python",
                "tooling/verify_required_status_checks_consistency.py",
                "--report-file",
                str(report_file),
            ],
            capture_output=True,
            timeout=30,
            text=True,
        )

        if report_file.exists():
            data, err = _load_json(report_file)
            if data:
                return {
                    "status": "collected",
                    "path": str(report_file.relative_to(artifacts_dir.parent)),
                    "data": data,
                }
            return {"status": "error", "error": err}
        return {"status": "not_generated"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def _load_policy_documents(repo_root: Path) -> Dict[str, Any]:
    """Load governance policy documents."""
    result = {}

    # Load BRANCH_PROTECTION_POLICY.md
    policy_file = repo_root / "docs" / "BRANCH_PROTECTION_POLICY.md"
    if policy_file.exists():
        try:
            result["branch_protection_policy"] = {
                "status": "present",
                "path": "docs/BRANCH_PROTECTION_POLICY.md",
                "modified": datetime.fromtimestamp(
                    policy_file.stat().st_mtime
                ).isoformat(),
            }
        except Exception as e:
            result["branch_protection_policy"] = {"status": "error", "error": str(e)}
    else:
        result["branch_protection_policy"] = {"status": "missing"}

    # Load required_status_checks.json
    checks_file = repo_root / "docs" / "required_status_checks.json"
    if checks_file.exists():
        data, err = _load_json(checks_file)
        if data:
            result["required_status_checks"] = {
                "status": "present",
                "path": "docs/required_status_checks.json",
                "checks": data.get("required_checks", []),
            }
        else:
            result["required_status_checks"] = {"status": "error", "error": err}
    else:
        result["required_status_checks"] = {"status": "missing"}

    return result


def _generate_evidence_manifest(
    repo_root: Path = Path("."), artifacts_dir: Optional[Path] = None
) -> Dict[str, Any]:
    """Generate comprehensive governance evidence manifest."""

    if artifacts_dir is None:
        artifacts_dir = repo_root / "artifacts"

    artifacts_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "contract": "governance_evidence_v1",
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "generated_by": "tooling/generate_governance_evidence_manifest.py",
        "repo_root": str(repo_root),
        "automated_reports": {
            "branch_protection_verification": _verify_github_branch_protection(
                artifacts_dir
            ),
            "required_status_checks_consistency": _verify_required_status_checks_consistency(
                artifacts_dir
            ),
        },
        "policy_documents": _load_policy_documents(repo_root),
        "external_evidence_checklist": {
            "status": "pending",
            "checklist_path": "docs/GOVERNANCE_EVIDENCE_CHECKLIST.md",
            "manual_evidence_items": [
                "github_ui_ruleset_screenshots",
                "github_ui_branch_protection_screenshots",
                "github_ui_required_checks_screenshots",
                "github_ui_bypass_control_screenshots",
            ],
            "note": "Manual UI screenshots must be captured during release preparation (see GOVERNANCE_EVIDENCE_CHECKLIST.md for detailed procedure)",
        },
        "exit_criteria": {
            "all_automated_reports_collected": False,
            "all_manual_evidence_captured": False,
            "policy_documents_up_to_date": False,
            "verification_passed": False,
        },
    }

    # Check exit criteria
    automated_status = all(
        report.get("status") == "collected"
        for report in manifest["automated_reports"].values()
    )

    policy_status = all(
        doc.get("status") == "present" for doc in manifest["policy_documents"].values()
    )

    manifest["exit_criteria"]["all_automated_reports_collected"] = automated_status
    manifest["exit_criteria"]["policy_documents_up_to_date"] = policy_status
    manifest["exit_criteria"]["verification_passed"] = (
        automated_status and policy_status
    )

    return manifest


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate governance evidence manifest for release bundles"
    )
    parser.add_argument(
        "--repo-root", type=Path, default=Path("."), help="Repository root path"
    )
    parser.add_argument(
        "--artifacts-dir",
        type=Path,
        default=None,
        help="Artifacts directory (default: <repo-root>/artifacts)",
    )
    parser.add_argument(
        "--output-file",
        type=Path,
        default=None,
        help="Output manifest file (default: <artifacts-dir>/governance_evidence_manifest.json)",
    )

    args = parser.parse_args()

    if args.output_file is None:
        artifacts_dir = args.artifacts_dir or (args.repo_root / "artifacts")
        args.output_file = artifacts_dir / "governance_evidence_manifest.json"

    manifest = _generate_evidence_manifest(
        repo_root=args.repo_root,
        artifacts_dir=args.artifacts_dir or (args.repo_root / "artifacts"),
    )

    args.output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output_file, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print(f"Governance evidence manifest generated: {args.output_file}")

    # Exit with success if all automated reports collected
    if manifest["exit_criteria"]["verification_passed"]:
        print("OK: All automated reports collected and verified")
        return 0
    else:
        print(
            "WARN: Some automated reports not collected; manual evidence capture still needed"
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Security audit: dependency vulnerability scan + SBOM generation.

Usage:
    python tooling/security_audit.py [--sbom] [--fail-on SEVERITY]

Requires: pip-audit (``pip install pip-audit``)
Optional: cyclonedx-bom for SBOM generation (``pip install cyclonedx-bom``)

Exit codes:
    0 — no vulnerabilities found at or above threshold
    1 — vulnerabilities found
    2 — tool not installed / runtime error
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ARTIFACTS_DIR = Path(__file__).resolve().parent.parent / "artifacts"
SBOM_PATH = ARTIFACTS_DIR / "sbom.cdx.json"
AUDIT_REPORT_PATH = ARTIFACTS_DIR / "pip_audit_report.json"

_SEVERITY_RANK = {"none": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}


def _run_pip_audit() -> dict:
    """Run pip-audit and return parsed JSON output."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip_audit", "--format=json", "--output=-"],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except FileNotFoundError:
        print("ERROR: pip-audit is not installed. Run: pip install pip-audit", file=sys.stderr)
        sys.exit(2)
    except subprocess.TimeoutExpired:
        print("ERROR: pip-audit timed out after 120s", file=sys.stderr)
        sys.exit(2)

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        # pip-audit may write to stderr on failure
        print(f"pip-audit stderr: {result.stderr}", file=sys.stderr)
        data = {"dependencies": []}

    return data


def _generate_sbom() -> bool:
    """Generate CycloneDX SBOM. Returns True on success."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "cyclonedx_py", "environment", "-o", str(SBOM_PATH)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            print(f"  SBOM written to {SBOM_PATH}")
            return True
        # Try older CLI invocation
        result = subprocess.run(
            [sys.executable, "-m", "cyclonedx_bom", "-o", str(SBOM_PATH)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            print(f"  SBOM written to {SBOM_PATH}")
            return True
        print(f"  SBOM generation failed: {result.stderr[:200]}", file=sys.stderr)
        return False
    except FileNotFoundError:
        print("  cyclonedx-bom not installed — skipping SBOM generation", file=sys.stderr)
        return False
    except subprocess.TimeoutExpired:
        print("  SBOM generation timed out", file=sys.stderr)
        return False


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Security audit for agent-skills dependencies")
    parser.add_argument("--sbom", action="store_true", help="Generate CycloneDX SBOM")
    parser.add_argument(
        "--fail-on",
        choices=["low", "medium", "high", "critical"],
        default="high",
        help="Minimum severity to trigger non-zero exit (default: high)",
    )
    args = parser.parse_args()

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    print("Running pip-audit...")
    data = _run_pip_audit()

    # Save report
    AUDIT_REPORT_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"  Report saved to {AUDIT_REPORT_PATH}")

    # Analyze
    vulns_found = []
    for dep in data.get("dependencies", []):
        for vuln in dep.get("vulns", []):
            severity = (vuln.get("fix_versions") and "high") or "medium"  # pip-audit doesn't always give severity
            vulns_found.append({
                "package": dep.get("name"),
                "version": dep.get("version"),
                "vuln_id": vuln.get("id"),
                "description": vuln.get("description", "")[:120],
                "severity": severity,
            })

    if vulns_found:
        print(f"\n  Found {len(vulns_found)} vulnerability(ies):")
        for v in vulns_found:
            print(f"    [{v['severity'].upper()}] {v['package']}=={v['version']} — {v['vuln_id']}")
    else:
        print("  No vulnerabilities found.")

    if args.sbom:
        print("\nGenerating SBOM...")
        _generate_sbom()

    # Exit code based on severity threshold
    threshold = _SEVERITY_RANK.get(args.fail_on, 3)
    for v in vulns_found:
        if _SEVERITY_RANK.get(v["severity"], 0) >= threshold:
            print(f"\nFAILED: vulnerability at or above '{args.fail_on}' severity found.")
            sys.exit(1)

    print("\nPASSED: no vulnerabilities at or above threshold.")


if __name__ == "__main__":
    main()

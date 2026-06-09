#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REGISTRY_ROOT = ROOT.parent / "agent-skill-registry"
DEFAULT_REPORT_FILE = ROOT / "artifacts" / "governance_tenancy_rollout_report.json"
GOVERNANCE_PREFIXES = ("identity.", "policy.", "provenance.", "security.")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Verify same_tenant rollout coverage for governance capabilities and "
            "publish a JSON evidence report."
        )
    )
    parser.add_argument(
        "--registry-root",
        type=Path,
        default=DEFAULT_REGISTRY_ROOT,
        help="Path to agent-skill-registry root.",
    )
    parser.add_argument(
        "--report-file",
        type=Path,
        default=DEFAULT_REPORT_FILE,
        help="Path to write JSON report.",
    )
    parser.add_argument(
        "--fail-on-side-effect-gaps",
        action="store_true",
        default=True,
        help=(
            "Fail when a governance capability with side_effects=true is missing "
            "same_tenant in safety.allowed_targets."
        ),
    )
    parser.add_argument(
        "--no-fail-on-side-effect-gaps",
        action="store_false",
        dest="fail_on_side_effect_gaps",
        help="Run informational mode without failing on side-effect gaps.",
    )
    return parser.parse_args()


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _collect_governance_capabilities(registry_root: Path) -> list[dict]:
    capabilities_dir = registry_root / "capabilities"
    entries: list[dict] = []

    for file_path in sorted(capabilities_dir.glob("*.yaml")):
        if file_path.name.startswith("_"):
            continue

        data = _load_yaml(file_path)
        capability_id = data.get("id")
        if not isinstance(capability_id, str):
            continue
        if not capability_id.startswith(GOVERNANCE_PREFIXES):
            continue

        properties = data.get("properties") if isinstance(data.get("properties"), dict) else {}
        safety = data.get("safety") if isinstance(data.get("safety"), dict) else {}
        allowed_targets = (
            safety.get("allowed_targets") if isinstance(safety.get("allowed_targets"), list) else []
        )

        entries.append(
            {
                "id": capability_id,
                "status": (
                    data.get("metadata", {}).get("status")
                    if isinstance(data.get("metadata"), dict)
                    else "unspecified"
                ),
                "side_effects": properties.get("side_effects") is True,
                "trust_level": safety.get("trust_level"),
                "requires_confirmation": safety.get("requires_confirmation"),
                "same_tenant": "same_tenant" in allowed_targets,
                "capability_file": f"capabilities/{file_path.name}",
            }
        )

    return entries


def main() -> int:
    args = _parse_args()
    entries = _collect_governance_capabilities(args.registry_root)

    side_effect_total = sum(1 for item in entries if item["side_effects"])
    same_tenant_total = sum(1 for item in entries if item["same_tenant"])
    side_effect_gaps = [
        item["id"]
        for item in entries
        if item["side_effects"] and not item["same_tenant"]
    ]

    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "contract": "governance_tenancy_rollout_v1",
        "status": "passed" if not side_effect_gaps else "failed",
        "summary": {
            "governance_capabilities_total": len(entries),
            "same_tenant_enabled": same_tenant_total,
            "side_effect_capabilities_total": side_effect_total,
            "side_effect_gaps_total": len(side_effect_gaps),
            "same_tenant_adoption_ratio": (
                round(same_tenant_total / len(entries), 4) if entries else 0.0
            ),
            "side_effect_coverage_ratio": (
                round((side_effect_total - len(side_effect_gaps)) / side_effect_total, 4)
                if side_effect_total
                else 1.0
            ),
        },
        "side_effect_gaps": side_effect_gaps,
        "capabilities": entries,
    }

    args.report_file.parent.mkdir(parents=True, exist_ok=True)
    args.report_file.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("Governance tenancy rollout verification completed.")
    print(f"- status: {report['status']}")
    print(
        "- same_tenant enabled: "
        f"{report['summary']['same_tenant_enabled']}/{report['summary']['governance_capabilities_total']}"
    )
    print(
        "- side_effect coverage: "
        f"{side_effect_total - len(side_effect_gaps)}/{side_effect_total}"
    )
    print(f"- report: {args.report_file}")

    if side_effect_gaps and args.fail_on_side_effect_gaps:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

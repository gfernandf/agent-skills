#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from runtime.policy_shadow import (
    MirrorExternalPolicyAdapter,
    PolicyDecisionInput,
    compare_decisions,
)


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REPORT = ROOT / "artifacts" / "policy_shadow_report.json"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Verify shadow policy parity between current internal baseline and optional external adapter decisions."
        )
    )
    parser.add_argument(
        "--report-file",
        type=Path,
        default=DEFAULT_REPORT,
        help="Path to write policy shadow JSON report.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    args.report_file.parent.mkdir(parents=True, exist_ok=True)

    adapter = MirrorExternalPolicyAdapter()

    scenarios = [
        PolicyDecisionInput(
            capability_id="test.cap",
            step_id="s1",
            safety={"trust_level": "standard"},
            context_trust_level="elevated",
            confirmed_capabilities=[],
        ),
        PolicyDecisionInput(
            capability_id="test.cap",
            step_id="s2",
            safety={"trust_level": "privileged"},
            context_trust_level="standard",
            confirmed_capabilities=[],
        ),
        PolicyDecisionInput(
            capability_id="test.cap",
            step_id="s3",
            safety={"requires_confirmation": True},
            context_trust_level="standard",
            confirmed_capabilities=[],
        ),
        PolicyDecisionInput(
            capability_id="test.cap",
            step_id="s4",
            safety={"requires_confirmation": True},
            context_trust_level="standard",
            confirmed_capabilities=["test.cap"],
        ),
        PolicyDecisionInput(
            capability_id="decision.task.delegate",
            step_id="s5",
            safety={"allowed_targets": ["same_tenant"]},
            context_trust_level="elevated",
            confirmed_capabilities=[],
            context_tenant_id="tenant-acme",
            target_tenant_id="tenant-acme",
        ),
        PolicyDecisionInput(
            capability_id="decision.task.delegate",
            step_id="s6",
            safety={"allowed_targets": ["same_tenant"]},
            context_trust_level="elevated",
            confirmed_capabilities=[],
            context_tenant_id="tenant-acme",
            target_tenant_id="tenant-beta",
        ),
    ]

    comparisons = [compare_decisions(s, adapter) for s in scenarios]
    mismatches = [item for item in comparisons if not item["equal"]]

    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "status": "passed" if not mismatches else "failed",
        "summary": {
            "total": len(comparisons),
            "matched": len(comparisons) - len(mismatches),
            "mismatched": len(mismatches),
            "match_ratio": (
                (len(comparisons) - len(mismatches)) / len(comparisons)
                if comparisons
                else 0.0
            ),
        },
        "comparisons": comparisons,
        "mismatches": mismatches,
    }

    args.report_file.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("Policy shadow parity summary")
    print(
        f"- matched: {report['summary']['matched']}/{report['summary']['total']}"
    )
    print(f"- match_ratio: {report['summary']['match_ratio']:.3f}")
    print(f"- report: {args.report_file}")

    return 1 if mismatches else 0


if __name__ == "__main__":
    raise SystemExit(main())

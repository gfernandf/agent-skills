#!/usr/bin/env python3
"""
Run a small smoke suite of critical capabilities.

Exit codes:
- 0: all smoke capabilities passed
- 1: at least one smoke capability failed or is misconfigured
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGISTRY_ROOT = ROOT.parent / "agent-skill-registry"
SMOKE_LIST_FILE = Path(__file__).resolve().parent / "smoke_capabilities.json"

# Import shared batch-test helpers
sys.path.insert(0, str(ROOT))
import test_capabilities_batch as batch  # noqa: E402

from runtime.binding_registry import BindingRegistry  # noqa: E402
from runtime.capability_loader import YamlCapabilityLoader  # noqa: E402


def load_smoke_list():
    data = json.loads(SMOKE_LIST_FILE.read_text(encoding="utf-8"))
    if not isinstance(data, list) or not all(isinstance(x, str) for x in data):
        raise ValueError("smoke_capabilities.json must be a JSON array of strings")
    return data


def parse_args():
    parser = argparse.ArgumentParser(description="Verify critical smoke capabilities.")
    parser.add_argument(
        "--report-file",
        type=Path,
        default=None,
        help="Optional path to write JSON report for CI/agent ingestion.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    smoke_capabilities = load_smoke_list()

    capability_loader = YamlCapabilityLoader(REGISTRY_ROOT)
    binding_registry = BindingRegistry(ROOT, REGISTRY_ROOT)
    all_capabilities = capability_loader.get_all_capabilities()

    failures = []
    passes = []

    print(f"Running smoke suite ({len(smoke_capabilities)} capabilities)...")

    for capability_id in smoke_capabilities:
        if capability_id not in all_capabilities:
            failures.append((capability_id, "Capability not found in registry"))
            continue

        binding = batch.select_binding_for_capability(binding_registry, capability_id)
        if binding is None:
            failures.append((capability_id, "No binding found"))
            continue

        test_input = batch.TEST_DATA.get(capability_id)
        if not test_input:
            failures.append((capability_id, "No test data defined in test_capabilities_batch.py"))
            continue

        success, reason, _ = batch.call_capability(capability_id, binding, test_input)
        if success:
            passes.append(capability_id)
        else:
            failures.append((capability_id, reason))

    report = {
        "total": len(smoke_capabilities),
        "passed": len(passes),
        "failed": len(failures),
        "pass_ids": passes,
        "failures": [{"capability": capability_id, "reason": reason} for capability_id, reason in failures],
    }

    if args.report_file is not None:
        args.report_file.parent.mkdir(parents=True, exist_ok=True)
        args.report_file.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("\nSMOKE RESULTS")
    print("=" * 60)
    print(f"PASS: {len(passes)}")
    for capability_id in passes:
        print(f"  - {capability_id}")

    print(f"\nFAIL: {len(failures)}")
    for capability_id, reason in failures:
        print(f"  - {capability_id}: {reason}")

    if failures:
        print("\nSmoke verification failed.")
        return 1

    print("\nSmoke verification passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

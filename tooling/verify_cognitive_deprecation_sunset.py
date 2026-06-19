#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import yaml


def _load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8-sig") as fh:
        data = yaml.safe_load(fh)
    return data if isinstance(data, dict) else {}


def _scan_deprecated_cognitive_capabilities(registry_root: Path) -> list[str]:
    capabilities_dir = registry_root / "capabilities"
    deprecated: list[str] = []

    for cap_file in sorted(capabilities_dir.glob("*.yaml")):
        if cap_file.name.startswith("_"):
            continue
        data = _load_yaml(cap_file)
        metadata = (
            data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
        )
        layer = metadata.get("layer")
        status = metadata.get("status")
        if layer == "cognitive" and status == "deprecated":
            cap_id = (
                data.get("id") if isinstance(data.get("id"), str) else cap_file.stem
            )
            deprecated.append(cap_id)

    return deprecated


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fail when deprecated cognitive capabilities remain in registry"
    )
    parser.add_argument(
        "--registry-root",
        type=Path,
        default=Path("../agent-skill-registry"),
        help="Path to agent-skill-registry root",
    )
    parser.add_argument(
        "--report-file",
        type=Path,
        default=Path("artifacts/cognitive_deprecation_sunset_report.json"),
        help="Output JSON report path",
    )
    args = parser.parse_args()

    deprecated = _scan_deprecated_cognitive_capabilities(args.registry_root)
    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "registry_root": str(args.registry_root),
        "status": "passed" if not deprecated else "failed",
        "deprecated_cognitive_count": len(deprecated),
        "deprecated_cognitive_capabilities": deprecated,
    }

    args.report_file.parent.mkdir(parents=True, exist_ok=True)
    args.report_file.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("Cognitive deprecation sunset report")
    print(f"- deprecated cognitive capabilities: {len(deprecated)}")
    print(f"- report: {args.report_file}")

    if deprecated:
        for cap_id in deprecated:
            print(f"  - {cap_id}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

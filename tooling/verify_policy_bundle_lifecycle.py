#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BUNDLE_ROOT = ROOT / "policies" / "opa"
DEFAULT_REPORT = ROOT / "artifacts" / "policy_bundle_lifecycle_report.json"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Verify baseline OPA policy bundle lifecycle contract files and "
            "decision-path compatibility for staged rollout governance."
        )
    )
    parser.add_argument(
        "--bundle-root",
        type=Path,
        default=DEFAULT_BUNDLE_ROOT,
        help="Path to the OPA bundle root directory.",
    )
    parser.add_argument(
        "--report-file",
        type=Path,
        default=DEFAULT_REPORT,
        help="Path to write JSON report.",
    )
    parser.add_argument(
        "--expected-decision-path",
        default="/v1/data/orca/policy/pre",
        help="Expected OPA decision API path.",
    )
    return parser.parse_args()


def _check(condition: bool, check_id: str, detail: str) -> dict[str, object]:
    return {
        "check_id": check_id,
        "passed": condition,
        "detail": detail,
    }


def main() -> int:
    args = _parse_args()
    args.report_file.parent.mkdir(parents=True, exist_ok=True)

    checks: list[dict[str, object]] = []

    bundle_root = args.bundle_root
    manifest_path = bundle_root / "bundle_manifest.json"
    rego_path = bundle_root / "policy_pre.rego"

    checks.append(
        _check(bundle_root.exists(), "bundle_root_exists", str(bundle_root))
    )
    checks.append(
        _check(manifest_path.exists(), "bundle_manifest_exists", str(manifest_path))
    )
    checks.append(_check(rego_path.exists(), "policy_rego_exists", str(rego_path)))

    manifest: dict[str, object] = {}
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            checks.append(_check(True, "manifest_json_valid", "valid json"))
        except Exception as exc:
            checks.append(_check(False, "manifest_json_valid", f"invalid json: {exc}"))

    if manifest:
        bundle_version = manifest.get("bundle_version")
        bundle_version_ok = (
            isinstance(bundle_version, str)
            and bool(bundle_version.strip())
            and re.fullmatch(r"\d+\.\d+\.\d+", bundle_version.strip()) is not None
        )
        checks.append(
            _check(
                bundle_version_ok,
                "manifest_bundle_version",
                str(bundle_version),
            )
        )

        policy_package = manifest.get("policy_package")
        checks.append(
            _check(
                policy_package == "orca.policy.pre",
                "manifest_policy_package",
                str(policy_package),
            )
        )

        decision_path = manifest.get("decision_path")
        checks.append(
            _check(
                decision_path == args.expected_decision_path,
                "manifest_decision_path",
                str(decision_path),
            )
        )

        compatibility = manifest.get("compatibility")
        checks.append(
            _check(
                isinstance(compatibility, dict),
                "manifest_compatibility_block",
                "present" if isinstance(compatibility, dict) else "missing",
            )
        )

        tenant_scope = manifest.get("tenant_scope")
        checks.append(
            _check(
                isinstance(tenant_scope, dict),
                "manifest_tenant_scope_block",
                "present" if isinstance(tenant_scope, dict) else "missing",
            )
        )
        if isinstance(tenant_scope, dict):
            checks.append(
                _check(
                    tenant_scope.get("mode") in {
                        "shared_with_tenant_constraints",
                        "tenant_scoped",
                    },
                    "manifest_tenant_scope_mode",
                    str(tenant_scope.get("mode")),
                )
            )
            checks.append(
                _check(
                    tenant_scope.get("tenant_selection") == "context_tenant_only",
                    "manifest_tenant_scope_selection",
                    str(tenant_scope.get("tenant_selection")),
                )
            )
            checks.append(
                _check(
                    tenant_scope.get("cross_tenant_allowed") is False,
                    "manifest_tenant_scope_cross_tenant_allowed",
                    str(tenant_scope.get("cross_tenant_allowed")),
                )
            )

        promotion_policy = manifest.get("promotion_policy")
        checks.append(
            _check(
                isinstance(promotion_policy, dict),
                "manifest_promotion_policy_block",
                "present" if isinstance(promotion_policy, dict) else "missing",
            )
        )
        if isinstance(promotion_policy, dict):
            checks.append(
                _check(
                    isinstance(promotion_policy.get("required_reviews"), int)
                    and int(promotion_policy.get("required_reviews")) >= 1,
                    "manifest_promotion_required_reviews",
                    str(promotion_policy.get("required_reviews")),
                )
            )
            checks.append(
                _check(
                    promotion_policy.get("enforce_requires_shadow_validation") is True,
                    "manifest_promotion_requires_shadow_validation",
                    str(promotion_policy.get("enforce_requires_shadow_validation")),
                )
            )
            checks.append(
                _check(
                    promotion_policy.get("require_bundle_version_bump") is True,
                    "manifest_promotion_requires_version_bump",
                    str(promotion_policy.get("require_bundle_version_bump")),
                )
            )

    if rego_path.exists():
        rego_text = rego_path.read_text(encoding="utf-8")
        checks.append(
            _check(
                "package orca.policy.pre" in rego_text,
                "rego_package",
                "package orca.policy.pre",
            )
        )
        checks.append(
            _check(
                "default result" in rego_text,
                "rego_default_result",
                "default result rule",
            )
        )

    path_check = urlparse(f"https://placeholder{args.expected_decision_path}").path
    checks.append(
        _check(
            path_check == args.expected_decision_path,
            "expected_decision_path_valid",
            args.expected_decision_path,
        )
    )

    passed = sum(1 for c in checks if c.get("passed") is True)
    total = len(checks)
    failed = total - passed
    pass_ratio = (passed / total) if total else 0.0

    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "status": "passed" if failed == 0 else "failed",
        "contract": "opa_policy_bundle_lifecycle_v2",
        "summary": {
            "total": total,
            "passed": passed,
            "failed": failed,
            "pass_ratio": pass_ratio,
        },
        "bundle_root": str(bundle_root),
        "checks": checks,
    }

    args.report_file.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("Policy bundle lifecycle summary")
    print(f"- passed: {passed}/{total}")
    print(f"- pass_ratio: {pass_ratio:.3f}")
    print(f"- report: {args.report_file}")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

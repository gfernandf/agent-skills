#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ARTIFACTS_DIR = ROOT / "artifacts"
DEFAULT_MANIFEST = ROOT / "policies" / "opa" / "bundle_manifest.json"
DEFAULT_REPORT = ROOT / "artifacts" / "policy_promotion_readiness_report.json"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate automated policy promotion readiness evidence from runtime "
            "canary artifacts and bundle promotion policy metadata."
        )
    )
    parser.add_argument(
        "--artifacts-dir",
        type=Path,
        default=DEFAULT_ARTIFACTS_DIR,
        help="Directory containing runtime canary report artifacts.",
    )
    parser.add_argument(
        "--manifest-file",
        type=Path,
        default=DEFAULT_MANIFEST,
        help="Path to policy bundle manifest.",
    )
    parser.add_argument(
        "--report-file",
        type=Path,
        default=DEFAULT_REPORT,
        help="Path to write readiness JSON report.",
    )
    return parser.parse_args()


def _read_json(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _status_passed(report: dict[str, object]) -> bool:
    return str(report.get("status", "")).lower() == "passed"


def main() -> int:
    args = _parse_args()
    args.report_file.parent.mkdir(parents=True, exist_ok=True)

    manifest = _read_json(args.manifest_file)

    durability = _read_json(args.artifacts_dir / "durability_contract_report.json")
    policy_shadow = _read_json(args.artifacts_dir / "policy_shadow_report.json")
    tenant = _read_json(args.artifacts_dir / "tenant_isolation_matrix_report.json")
    bundle = _read_json(args.artifacts_dir / "policy_bundle_lifecycle_report.json")
    coverage = _read_json(args.artifacts_dir / "runtime_coverage.json")
    executability = _read_json(args.artifacts_dir / "skill_executability.json")

    coverage_ratio = float(coverage.get("coverage_ratio", 0.0) or 0.0)
    executability_ratio = float(executability.get("executability_ratio", 0.0) or 0.0)

    checks = {
        "durability_passed": _status_passed(durability),
        "policy_shadow_passed": _status_passed(policy_shadow),
        "tenant_isolation_passed": _status_passed(tenant),
        "bundle_lifecycle_passed": _status_passed(bundle),
        "coverage_ratio_passed": coverage_ratio >= 1.0,
        "executability_ratio_passed": executability_ratio >= 1.0,
    }

    total_automated = len(checks)
    passed_automated = sum(1 for ok in checks.values() if ok)
    runtime_canary_pass_ratio = (
        float(passed_automated) / float(total_automated) if total_automated else 0.0
    )

    promotion_policy = manifest.get("promotion_policy", {})
    if not isinstance(promotion_policy, dict):
        promotion_policy = {}

    env_promotion = promotion_policy.get("environment_promotion", {})
    if not isinstance(env_promotion, dict):
        env_promotion = {}

    rules = env_promotion.get("rules", {})
    if not isinstance(rules, dict):
        rules = {}

    dev_to_staging = rules.get("dev_to_staging", {})
    if not isinstance(dev_to_staging, dict):
        dev_to_staging = {}

    staging_to_prod = rules.get("staging_to_prod", {})
    if not isinstance(staging_to_prod, dict):
        staging_to_prod = {}

    d2s_min_ratio = float(dev_to_staging.get("min_runtime_canary_pass_ratio", 1.0) or 1.0)
    d2s_requires_shadow = bool(dev_to_staging.get("require_shadow_parity", False))

    s2p_min_ratio = float(
        staging_to_prod.get("min_runtime_canary_pass_ratio", 1.0) or 1.0
    )
    s2p_requires_shadow = bool(staging_to_prod.get("require_shadow_parity", False))
    s2p_required_approvals = int(staging_to_prod.get("required_approvals", 0) or 0)

    d2s_ready = (
        checks["bundle_lifecycle_passed"]
        and checks["tenant_isolation_passed"]
        and runtime_canary_pass_ratio >= d2s_min_ratio
        and (checks["policy_shadow_passed"] if d2s_requires_shadow else True)
    )

    s2p_automated_ready = (
        d2s_ready
        and checks["durability_passed"]
        and runtime_canary_pass_ratio >= s2p_min_ratio
        and (checks["policy_shadow_passed"] if s2p_requires_shadow else True)
    )

    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "status": "passed" if s2p_automated_ready else "failed",
        "contract": "policy_promotion_readiness_v1",
        "summary": {
            "automated_checks_total": total_automated,
            "automated_checks_passed": passed_automated,
            "automated_checks_failed": total_automated - passed_automated,
            "runtime_canary_pass_ratio": runtime_canary_pass_ratio,
            "coverage_ratio": coverage_ratio,
            "executability_ratio": executability_ratio,
        },
        "checks": checks,
        "environments": {
            "dev_to_staging": {
                "ready": d2s_ready,
                "requires_shadow_parity": d2s_requires_shadow,
                "required_min_runtime_canary_pass_ratio": d2s_min_ratio,
            },
            "staging_to_prod": {
                "automated_ready": s2p_automated_ready,
                "requires_shadow_parity": s2p_requires_shadow,
                "required_min_runtime_canary_pass_ratio": s2p_min_ratio,
                "required_approvals": s2p_required_approvals,
                "manual_approvals_pending": s2p_required_approvals > 0,
            },
        },
    }

    args.report_file.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("Policy promotion readiness summary")
    print(f"- status: {report['status']}")
    print(f"- runtime_canary_pass_ratio: {runtime_canary_pass_ratio:.3f}")
    print(f"- dev_to_staging.ready: {d2s_ready}")
    print(f"- staging_to_prod.automated_ready: {s2p_automated_ready}")
    print(f"- report: {args.report_file}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

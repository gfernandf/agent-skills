#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
REGISTRY_ROOT = ROOT.parent / "agent-skill-registry"
DEFAULT_REPORT = ROOT / "artifacts" / "tenant_isolation_matrix_report.json"
REQUIRED_SAME_TENANT_CAPABILITIES: tuple[str, ...] = (
    "decision.task.delegate.yaml",
    "web.request.send.yaml",
    "email.message.send.yaml",
    "message.notification.send.yaml",
    "agent.plan.execute.yaml",
    "decision.flow.branch.yaml",
    "data.schema.validate.yaml",
    "data.json.parse.yaml",
    "identity.role.assign.yaml",
    "identity.permission.gate.yaml",
    "identity.permission.get.yaml",
    "identity.permission.list.yaml",
    "identity.permission.verify.yaml",
    "identity.role.get.yaml",
    "identity.role.list.yaml",
    "policy.constraint.validate.yaml",
    "policy.constraint.gate.yaml",
    "policy.decision.evaluate.yaml",
    "policy.decision.justify.yaml",
    "policy.record.classify.yaml",
    "policy.risk.classify.yaml",
    "policy.risk.score.yaml",
)


@dataclass
class CheckResult:
    surface: str
    check_id: str
    passed: bool
    detail: str
    duration_seconds: float


PYTEST_TENANT_NODES: list[tuple[str, str]] = [
    (
        "runtime_identity",
        "runtime/test_auth.py::TestMultiTenancy::test_extract_tenant_from_jwt_claims",
    ),
    (
        "runtime_identity",
        "runtime/test_auth.py::TestMultiTenancy::test_extract_tenant_from_metadata",
    ),
    (
        "runtime_identity",
        "runtime/test_auth.py::TestMultiTenancy::test_jwt_tenant_claim_in_verifier",
    ),
    ("runtime_persistence", "runtime/test_run_store.py::test_create_run_record_v2"),
    (
        "runtime_policy",
        "runtime/test_safety.py::test_same_tenant_requires_context",
    ),
    (
        "runtime_policy",
        "runtime/test_safety.py::test_same_tenant_mismatch_blocked",
    ),
    (
        "runtime_policy",
        "runtime/test_safety.py::test_same_tenant_matching_allows_execution",
    ),
    (
        "channel_tenancy",
        "test_neutral_api_slice2.py::test_execute_skill_async_propagates_tenant_to_execution_options",
    ),
    (
        "channel_tenancy",
        "test_neutral_api_slice2.py::test_resume_run_propagates_tenant_from_run_metadata",
    ),
    (
        "channel_tenancy",
        "test_neutral_api_slice2.py::test_replay_run_propagates_tenant_to_replay_execution",
    ),
    (
        "transport_tenancy",
        "test_customer_transport_tenancy.py::test_http_tenant_resolution_prefers_authenticated_identity",
    ),
    (
        "transport_tenancy",
        "test_customer_transport_tenancy.py::test_http_tenant_resolution_does_not_accept_body_override_with_auth",
    ),
    (
        "transport_tenancy",
        "test_customer_transport_tenancy.py::test_http_tenant_resolution_uses_body_when_auth_disabled",
    ),
    (
        "transport_tenancy",
        "test_customer_transport_tenancy.py::test_mcp_skill_execute_propagates_tenant_id",
    ),
]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Verify tenant isolation consistency matrix across runtime identity, "
            "run persistence, runtime same_tenant policy checks, and registry tenancy artifacts."
        )
    )
    parser.add_argument(
        "--report-file",
        type=Path,
        default=DEFAULT_REPORT,
        help="Path to write JSON report.",
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Continue running checks after failures.",
    )
    parser.add_argument(
        "--enforce-registry-capabilities",
        action="store_true",
        help=(
            "Fail when required registry capabilities are missing same_tenant adoption. "
            "By default these checks are informational to avoid pin-drift false negatives."
        ),
    )
    return parser.parse_args()


def _run_pytest_node(surface: str, nodeid: str) -> CheckResult:
    command = [sys.executable, "-m", "pytest", "-q", "-o", "addopts=", nodeid]
    start = time.perf_counter()
    proc = subprocess.run(command, cwd=ROOT)
    duration = time.perf_counter() - start
    return CheckResult(
        surface=surface,
        check_id=nodeid,
        passed=proc.returncode == 0,
        detail="ok" if proc.returncode == 0 else f"pytest_returncode={proc.returncode}",
        duration_seconds=duration,
    )


def _check_registry_vocabulary(
    enforce_registry_capabilities: bool,
) -> list[CheckResult]:
    checks: list[CheckResult] = []

    vocab_file = REGISTRY_ROOT / "vocabulary" / "safety_vocabulary.yaml"
    start = time.perf_counter()
    vocab_ok = False
    vocab_detail = "file_missing"
    if vocab_file.exists():
        content = vocab_file.read_text(encoding="utf-8")
        vocab_ok = "same_tenant:" in content
        vocab_detail = "same_tenant_present" if vocab_ok else "same_tenant_missing"
    checks.append(
        CheckResult(
            surface="registry_vocabulary",
            check_id="vocabulary/safety_vocabulary.yaml:same_tenant",
            passed=vocab_ok,
            detail=vocab_detail,
            duration_seconds=time.perf_counter() - start,
        )
    )

    docs_file = REGISTRY_ROOT / "docs" / "CAPABILITIES.md"
    start = time.perf_counter()
    docs_ok = False
    docs_detail = "file_missing"
    if docs_file.exists():
        content = docs_file.read_text(encoding="utf-8")
        docs_ok = "same_tenant" in content
        docs_detail = (
            "same_tenant_documented" if docs_ok else "same_tenant_not_documented"
        )
    checks.append(
        CheckResult(
            surface="registry_vocabulary",
            check_id="docs/CAPABILITIES.md:same_tenant",
            passed=docs_ok,
            detail=docs_detail,
            duration_seconds=time.perf_counter() - start,
        )
    )

    adopted_count = 0
    for capability_name in REQUIRED_SAME_TENANT_CAPABILITIES:
        capability_file = REGISTRY_ROOT / "capabilities" / capability_name
        start = time.perf_counter()
        capability_ok = False
        capability_detail = "file_missing"
        if capability_file.exists():
            content = capability_file.read_text(encoding="utf-8")
            capability_ok = "- same_tenant" in content
            capability_detail = (
                "same_tenant_adopted" if capability_ok else "same_tenant_not_adopted"
            )
        if capability_ok:
            adopted_count += 1
        checks.append(
            CheckResult(
                surface="registry_capabilities",
                check_id=f"capabilities/{capability_name}:same_tenant",
                passed=capability_ok or not enforce_registry_capabilities,
                detail=capability_detail,
                duration_seconds=time.perf_counter() - start,
            )
        )

    threshold_ok = (
        adopted_count >= len(REQUIRED_SAME_TENANT_CAPABILITIES)
        or not enforce_registry_capabilities
    )
    checks.append(
        CheckResult(
            surface="registry_capabilities",
            check_id="capabilities:same_tenant_adoption_threshold",
            passed=threshold_ok,
            detail=(
                f"adopted={adopted_count}/{len(REQUIRED_SAME_TENANT_CAPABILITIES)}"
            ),
            duration_seconds=0.0,
        )
    )

    return checks


def main() -> int:
    args = _parse_args()
    args.report_file.parent.mkdir(parents=True, exist_ok=True)

    print("Running tenant isolation consistency matrix verification...")

    results: list[CheckResult] = []

    for surface, nodeid in PYTEST_TENANT_NODES:
        print(f"[tenant-matrix] pytest -q {nodeid}")
        result = _run_pytest_node(surface, nodeid)
        results.append(result)
        if not result.passed and not args.continue_on_error:
            break

    if args.continue_on_error or all(r.passed for r in results):
        registry_checks = _check_registry_vocabulary(
            enforce_registry_capabilities=args.enforce_registry_capabilities
        )
        for check in registry_checks:
            print(f"[tenant-matrix] {check.check_id}: {check.detail}")
        results.extend(registry_checks)

    passed = sum(1 for r in results if r.passed)
    total = len(results)
    failed = total - passed
    pass_ratio = (passed / total) if total else 0.0

    by_surface: dict[str, dict[str, int]] = {}
    for result in results:
        surface_summary = by_surface.setdefault(
            result.surface, {"total": 0, "passed": 0, "failed": 0}
        )
        surface_summary["total"] += 1
        if result.passed:
            surface_summary["passed"] += 1
        else:
            surface_summary["failed"] += 1

    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "status": "passed" if failed == 0 else "failed",
        "contract": "tenant_isolation_matrix_v1",
        "summary": {
            "total": total,
            "passed": passed,
            "failed": failed,
            "pass_ratio": pass_ratio,
        },
        "by_surface": by_surface,
        "checks": [
            {
                "surface": r.surface,
                "check_id": r.check_id,
                "passed": r.passed,
                "detail": r.detail,
                "duration_seconds": round(r.duration_seconds, 3),
            }
            for r in results
        ],
    }

    args.report_file.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("\nTenant isolation matrix summary")
    print(f"- passed: {passed}/{total}")
    print(f"- pass_ratio: {pass_ratio:.3f}")
    print(f"- report: {args.report_file}")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

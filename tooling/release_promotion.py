from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tooling.release_bundle import (
    _read_current_pointer,
    _read_json,
    _resolve_evidence_path,
    promote_release_bundle,
    verify_release_bundle,
)


PROMOTION_REPORT_CONTRACT = "release_bundle_promotion_v1"
RELEASE_GATE_CONTRACT = "release_readiness_gate_v1"
PROMOTION_READINESS_CONTRACT = "policy_promotion_readiness_v1"
ALLOWED_SEQUENCE = {
    "preview": {None},
    "dev": {None, "preview"},
    "staging": {"dev"},
    "prod": {"staging"},
}


@dataclass
class PromotionEvaluationResult:
    ok: bool
    checks: list[dict[str, Any]]
    gate_decision: str | None
    promotion_status: str | None
    source_bundle_match: bool | None


def _append_check(
    checks: list[dict[str, Any]],
    *,
    check_id: str,
    passed: bool,
    detail: str,
) -> None:
    checks.append({"check_id": check_id, "passed": passed, "detail": detail})


def _status_is_pass(value: Any) -> bool:
    return isinstance(value, str) and value.strip().lower() in {
        "pass",
        "passed",
        "ok",
        "success",
    }


def _load_bundle_evidence(
    bundle_root: Path, name: str
) -> tuple[dict[str, Any] | None, str | None]:
    evidence_root = bundle_root / "evidence"
    path = evidence_root / name
    if not path.exists():
        return None, f"missing:{path}"
    try:
        payload = _read_json(path)
    except Exception as exc:
        return None, f"invalid_json:{exc}"
    if not isinstance(payload, dict):
        return None, "invalid_shape"
    return payload, None


def _load_evidence(
    bundle_root: Path,
    name: str,
    artifacts_dir: Path | None,
) -> tuple[dict[str, Any] | None, str | None, str]:
    if artifacts_dir is not None:
        external_path = _resolve_evidence_path(artifacts_dir, name)
        if external_path is not None:
            try:
                payload = _read_json(external_path)
            except Exception as exc:
                return None, f"invalid_json:{exc}", f"external:{external_path}"
            if not isinstance(payload, dict):
                return None, "invalid_shape", f"external:{external_path}"
            return payload, None, f"external:{external_path}"
    payload, error = _load_bundle_evidence(bundle_root, name)
    return payload, error, "bundle"


def evaluate_bundle_promotion(
    *,
    bundle_root: Path,
    environment: str,
    deployment_root: Path,
    source_environment: str | None,
    artifacts_dir: Path | None = None,
) -> PromotionEvaluationResult:
    checks: list[dict[str, Any]] = []

    verify = verify_release_bundle(bundle_root=bundle_root)
    _append_check(
        checks,
        check_id="bundle_verify_ok",
        passed=verify.ok,
        detail=(
            f"bundle_id={verify.bundle_id}; verified_files={verify.verified_files}; errors={verify.errors}"
        ),
    )
    if not verify.ok:
        return PromotionEvaluationResult(
            ok=False,
            checks=checks,
            gate_decision=None,
            promotion_status=None,
            source_bundle_match=None,
        )

    allowed_sources = ALLOWED_SEQUENCE.get(environment)
    transition_ok = (
        allowed_sources is not None and source_environment in allowed_sources
    )
    _append_check(
        checks,
        check_id="environment_transition_allowed",
        passed=transition_ok,
        detail=f"source_environment={source_environment}; target_environment={environment}",
    )

    gate_report, gate_error, gate_source = _load_evidence(
        bundle_root, "release_readiness_gate_report.json", artifacts_dir
    )
    gate_decision = (
        str(gate_report.get("decision"))
        if isinstance(gate_report, dict) and gate_report.get("decision") is not None
        else None
    )
    gate_status = (
        str(gate_report.get("status"))
        if isinstance(gate_report, dict) and gate_report.get("status") is not None
        else None
    )
    gate_contract = (
        str(gate_report.get("contract"))
        if isinstance(gate_report, dict) and gate_report.get("contract") is not None
        else None
    )
    gate_contract_ok = gate_error is None and gate_contract == RELEASE_GATE_CONTRACT
    _append_check(
        checks,
        check_id="release_gate_contract_valid",
        passed=gate_contract_ok,
        detail=f"contract={gate_contract}; error={gate_error}; source={gate_source}",
    )
    gate_required_ok = False
    if gate_error is None and gate_contract_ok:
        if environment in {"preview", "dev"}:
            gate_required_ok = gate_decision in {"go", "conditional-go"}
        else:
            gate_required_ok = gate_decision == "go" and gate_status == "passed"
    _append_check(
        checks,
        check_id="release_gate_allows_promotion",
        passed=gate_required_ok,
        detail=f"decision={gate_decision}; status={gate_status}; error={gate_error}; source={gate_source}",
    )

    promotion_report, promotion_error, promotion_source = _load_evidence(
        bundle_root, "policy_promotion_readiness_report.json", artifacts_dir
    )
    promotion_status = (
        str(promotion_report.get("status"))
        if isinstance(promotion_report, dict)
        and promotion_report.get("status") is not None
        else None
    )
    promotion_contract = (
        str(promotion_report.get("contract"))
        if isinstance(promotion_report, dict)
        and promotion_report.get("contract") is not None
        else None
    )
    promotion_contract_ok = (
        promotion_error is None and promotion_contract == PROMOTION_READINESS_CONTRACT
    )
    _append_check(
        checks,
        check_id="promotion_readiness_contract_valid",
        passed=promotion_contract_ok,
        detail=(
            f"contract={promotion_contract}; error={promotion_error}; "
            f"source={promotion_source}"
        ),
    )
    promotion_status_ok = promotion_error is None and _status_is_pass(promotion_status)
    _append_check(
        checks,
        check_id="promotion_readiness_status_passed",
        passed=promotion_status_ok,
        detail=(
            f"status={promotion_status}; error={promotion_error}; source={promotion_source}"
        ),
    )
    envs = (
        promotion_report.get("environments", {})
        if isinstance(promotion_report, dict)
        and isinstance(promotion_report.get("environments"), dict)
        else {}
    )
    d2s = (
        envs.get("dev_to_staging", {})
        if isinstance(envs.get("dev_to_staging"), dict)
        else {}
    )
    s2p = (
        envs.get("staging_to_prod", {})
        if isinstance(envs.get("staging_to_prod"), dict)
        else {}
    )

    if environment == "staging":
        promotion_ready = (
            promotion_contract_ok and promotion_status_ok and d2s.get("ready") is True
        )
    elif environment == "prod":
        promotion_ready = (
            promotion_contract_ok
            and promotion_status_ok
            and s2p.get("automated_ready") is True
        )
    else:
        promotion_ready = promotion_contract_ok and promotion_status_ok

    _append_check(
        checks,
        check_id="promotion_readiness_allows_target_env",
        passed=promotion_ready,
        detail=f"target_environment={environment}; status={promotion_status}; error={promotion_error}; source={promotion_source}",
    )

    source_bundle_match: bool | None = None
    if source_environment is not None:
        source_current = _read_current_pointer(
            deployment_root / source_environment / "current.json"
        )
        source_bundle_id = (
            source_current.get("bundle_id")
            if isinstance(source_current, dict)
            else None
        )
        source_bundle_match = source_bundle_id == verify.bundle_id
        _append_check(
            checks,
            check_id="source_environment_has_same_bundle",
            passed=source_bundle_match,
            detail=f"source_environment={source_environment}; source_bundle_id={source_bundle_id}; target_bundle_id={verify.bundle_id}",
        )

    ok = all(bool(item.get("passed")) for item in checks)
    return PromotionEvaluationResult(
        ok=ok,
        checks=checks,
        gate_decision=gate_decision,
        promotion_status=promotion_status,
        source_bundle_match=source_bundle_match,
    )


def execute_bundle_promotion(
    *,
    bundle_root: Path,
    environment: str,
    deployment_root: Path,
    source_environment: str | None,
    report_file: Path,
    artifacts_dir: Path | None = None,
) -> int:
    report_file.parent.mkdir(parents=True, exist_ok=True)
    evaluation = evaluate_bundle_promotion(
        bundle_root=bundle_root,
        environment=environment,
        deployment_root=deployment_root,
        source_environment=source_environment,
        artifacts_dir=artifacts_dir,
    )

    result_payload: dict[str, Any] = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "contract": PROMOTION_REPORT_CONTRACT,
        "status": "failed",
        "environment": environment,
        "source_environment": source_environment,
        "bundle_root": str(bundle_root),
        "checks": evaluation.checks,
        "gate_decision": evaluation.gate_decision,
        "promotion_readiness_status": evaluation.promotion_status,
    }

    if evaluation.ok:
        promote = promote_release_bundle(
            bundle_root=bundle_root,
            deployment_root=deployment_root,
            environment=environment,
        )
        result_payload.update(
            {
                "status": "passed",
                "bundle_id": promote.bundle_id,
                "release_root": str(promote.release_root),
                "current_pointer": str(promote.current_pointer),
                "previous_bundle_id": promote.previous_bundle_id,
            }
        )
    else:
        verify = verify_release_bundle(bundle_root=bundle_root)
        result_payload["bundle_id"] = verify.bundle_id

    report_file.write_text(json.dumps(result_payload, indent=2), encoding="utf-8")
    print("Release bundle promotion")
    print(f"- environment: {environment}")
    print(f"- source_environment: {source_environment}")
    print(f"- status: {result_payload['status']}")
    print(f"- bundle_id: {result_payload.get('bundle_id')}")
    print(f"- report: {report_file}")
    return 0 if evaluation.ok else 1


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate and execute gated release bundle promotion."
    )
    parser.add_argument("bundle_path", type=Path)
    parser.add_argument(
        "--environment",
        required=True,
        choices=["preview", "dev", "staging", "prod"],
    )
    parser.add_argument(
        "--deployment-root",
        type=Path,
        default=Path("artifacts") / "deployments",
    )
    parser.add_argument(
        "--source-environment",
        default=None,
        choices=["preview", "dev", "staging"],
        help="Optional source environment that must already be running the same bundle.",
    )
    parser.add_argument(
        "--report-file",
        type=Path,
        default=Path("artifacts") / "release_bundle_promotion_report.json",
    )
    parser.add_argument(
        "--artifacts-dir",
        type=Path,
        default=None,
        help="Optional artifacts directory whose evidence overrides bundled evidence for gate/readiness evaluation.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    return execute_bundle_promotion(
        bundle_root=args.bundle_path,
        environment=args.environment,
        deployment_root=args.deployment_root,
        source_environment=args.source_environment,
        report_file=args.report_file,
        artifacts_dir=args.artifacts_dir,
    )


if __name__ == "__main__":
    raise SystemExit(main())

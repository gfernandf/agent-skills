#!/usr/bin/env python3
"""Audit OpenAPI runtime guardrails across official bindings.

This script enforces a global latency policy so timeout regressions are found
proactively instead of by brute-force runtime probing.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
REGISTRY_ROOT = ROOT.parent / "agent-skill-registry"

import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime.binding_registry import BindingRegistry  # noqa: E402


CRITICAL_CAPABILITY_PREFIXES: tuple[str, ...] = (
    "decision.",
    "analysis.",
    "eval.",
    "agent.option.",
    "agent.plan.",
    "agent.output.",
)

PROFILE_POLICY: dict[str, dict[str, Any]] = {
    "critical": {
        "min_timeout_seconds": 30,
        "recommended_timeout_seconds": 45,
    },
    "standard": {
        "min_timeout_seconds": 20,
        "recommended_timeout_seconds": 30,
    },
}

MAX_RETRY_RECOMMENDED = 1


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="audit_openapi_runtime_guardrails",
        description=(
            "Audit OpenAPI binding timeout/retry guardrails and generate a "
            "machine-readable report."
        ),
    )
    parser.add_argument(
        "--runtime-root",
        type=Path,
        default=ROOT,
        help="Path to agent-skills repository root.",
    )
    parser.add_argument(
        "--registry-root",
        type=Path,
        default=REGISTRY_ROOT,
        help="Path to agent-skill-registry repository root.",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=ROOT / "artifacts" / "openapi_runtime_guardrails.json",
        help="Output report JSON path.",
    )
    parser.add_argument(
        "--include-non-openai",
        action="store_true",
        help="Also audit non-OpenAI OpenAPI bindings.",
    )
    parser.add_argument(
        "--fail-on",
        choices=("none", "medium", "high"),
        default="high",
        help="Failure threshold for findings severity.",
    )
    return parser.parse_args()


def _is_openai_service(service_id: str, service_base_url: str | None) -> bool:
    service_id_norm = service_id.lower()
    if "openai" in service_id_norm:
        return True
    if isinstance(service_base_url, str) and "api.openai.com" in service_base_url:
        return True
    return False


def _profile_for_capability(capability_id: str) -> str:
    for prefix in CRITICAL_CAPABILITY_PREFIXES:
        if capability_id.startswith(prefix):
            return "critical"
    return "standard"


def _to_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if value.is_integer():
            return int(value)
        return None
    return None


def _evaluate_binding(binding: Any, service: Any) -> dict[str, Any]:
    metadata = binding.metadata if isinstance(binding.metadata, dict) else {}
    timeout_seconds_raw = metadata.get("timeout_seconds")
    timeout_seconds = _to_int(timeout_seconds_raw)
    retry_count = _to_int(metadata.get("retry_count"))
    if retry_count is None:
        retry_count = 0

    profile = _profile_for_capability(binding.capability_id)
    policy = PROFILE_POLICY[profile]
    min_timeout = int(policy["min_timeout_seconds"])
    recommended_timeout = int(policy["recommended_timeout_seconds"])

    findings: list[dict[str, Any]] = []

    if timeout_seconds is None:
        findings.append(
            {
                "id": "missing_timeout",
                "severity": "high",
                "message": (
                    "OpenAPI binding does not declare metadata.timeout_seconds."
                ),
                "expected": {
                    "min_timeout_seconds": min_timeout,
                    "recommended_timeout_seconds": recommended_timeout,
                },
            }
        )
    elif timeout_seconds < min_timeout:
        findings.append(
            {
                "id": "timeout_too_low",
                "severity": "high" if profile == "critical" else "medium",
                "message": (
                    f"Timeout ({timeout_seconds}s) below minimum for profile "
                    f"'{profile}' ({min_timeout}s)."
                ),
                "expected": {
                    "min_timeout_seconds": min_timeout,
                    "recommended_timeout_seconds": recommended_timeout,
                },
            }
        )

    if retry_count > MAX_RETRY_RECOMMENDED:
        findings.append(
            {
                "id": "retry_too_high",
                "severity": "medium",
                "message": (
                    f"retry_count ({retry_count}) is above recommended max "
                    f"({MAX_RETRY_RECOMMENDED})."
                ),
                "expected": {"max_retry_count": MAX_RETRY_RECOMMENDED},
            }
        )

    proposed_timeout = timeout_seconds
    if proposed_timeout is None or proposed_timeout < min_timeout:
        proposed_timeout = recommended_timeout

    return {
        "binding_id": binding.id,
        "capability_id": binding.capability_id,
        "service_id": binding.service_id,
        "service_base_url": service.base_url,
        "profile": profile,
        "current": {
            "timeout_seconds": timeout_seconds_raw,
            "retry_count": retry_count,
            "fallback_binding_id": metadata.get("fallback_binding_id"),
        },
        "policy": {
            "min_timeout_seconds": min_timeout,
            "recommended_timeout_seconds": recommended_timeout,
            "max_retry_count": MAX_RETRY_RECOMMENDED,
        },
        "proposed": {
            "timeout_seconds": proposed_timeout,
            "retry_count": retry_count,
        },
        "findings": findings,
        "status": "pass" if not findings else "fail",
        "source_file": binding.source_file,
    }


def build_report(
    runtime_root: Path, registry_root: Path, include_non_openai: bool
) -> dict[str, Any]:
    binding_registry = BindingRegistry(runtime_root, registry_root)
    entries: list[dict[str, Any]] = []

    for binding in binding_registry.list_bindings():
        if binding.source != "official":
            continue
        if binding.protocol != "openapi":
            continue

        service = binding_registry.get_service(binding.service_id)
        if not include_non_openai and not _is_openai_service(
            binding.service_id, service.base_url
        ):
            continue

        entries.append(_evaluate_binding(binding, service))

    total = len(entries)
    failed = sum(1 for entry in entries if entry["status"] == "fail")
    findings = [finding for entry in entries for finding in entry["findings"]]
    high = sum(1 for finding in findings if finding["severity"] == "high")
    medium = sum(1 for finding in findings if finding["severity"] == "medium")

    return {
        "schema_version": "1.0",
        "policy": {
            "profiles": PROFILE_POLICY,
            "critical_capability_prefixes": list(CRITICAL_CAPABILITY_PREFIXES),
            "retry_strategy": (
                "Timeout is primary control. Keep retry_count <= 1 to avoid "
                "latency amplification while preserving resilience for transient failures."
            ),
            "max_retry_recommended": MAX_RETRY_RECOMMENDED,
        },
        "summary": {
            "bindings_scanned": total,
            "bindings_failed": failed,
            "findings_total": len(findings),
            "findings_high": high,
            "findings_medium": medium,
        },
        "entries": entries,
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def _should_fail(report: dict[str, Any], threshold: str) -> bool:
    if threshold == "none":
        return False

    summary = report.get("summary", {})
    high = int(summary.get("findings_high", 0))
    medium = int(summary.get("findings_medium", 0))

    if threshold == "high":
        return high > 0
    return high > 0 or medium > 0


def main() -> int:
    args = _parse_args()
    runtime_root = args.runtime_root.resolve()
    registry_root = args.registry_root.resolve()
    report_path = args.report.resolve()

    report = build_report(runtime_root, registry_root, args.include_non_openai)
    _write_json(report_path, report)

    summary = report.get("summary", {})
    print("OPENAPI RUNTIME GUARDRAILS GENERATED")
    print(f"Bindings scanned: {summary.get('bindings_scanned', 0)}")
    print(f"Bindings failed: {summary.get('bindings_failed', 0)}")
    print(f"Findings high: {summary.get('findings_high', 0)}")
    print(f"Findings medium: {summary.get('findings_medium', 0)}")
    print(f"Written: {report_path.as_posix()}")

    if _should_fail(report, args.fail_on):
        print(f"FAILED: findings at severity threshold '{args.fail_on}'.")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

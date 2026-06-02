#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REPORT = ROOT / "artifacts" / "release_lineage.json"
DEFAULT_MARKDOWN = ROOT / "artifacts" / "release_lineage.md"
LINEAGE_CONTRACT = "release_lineage_v1"
LINEAGE_SCHEMA_VERSION = "1.1"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate release lineage artifact from workflow job context and produced reports."
    )
    parser.add_argument(
        "--needs-json",
        default="{}",
        help="JSON object from GitHub Actions needs context (for example: ${{ toJson(needs) }}).",
    )
    parser.add_argument(
        "--needs-file",
        type=Path,
        default=None,
        help="Optional path to a JSON file containing GitHub Actions needs context.",
    )
    parser.add_argument(
        "--artifacts-dir",
        type=Path,
        default=ROOT / "artifacts",
        help="Directory where downloaded/generated artifacts are available.",
    )
    parser.add_argument(
        "--report-file",
        type=Path,
        default=DEFAULT_REPORT,
        help="Path for lineage JSON output.",
    )
    parser.add_argument(
        "--markdown-file",
        type=Path,
        default=DEFAULT_MARKDOWN,
        help="Path for lineage markdown output.",
    )
    parser.add_argument(
        "--fail-on-incomplete",
        action="store_true",
        help="Exit non-zero when lineage completeness checks fail.",
    )
    return parser.parse_args()


def _resolve_needs_json_arg(raw: str) -> str:
    if isinstance(raw, str) and raw.startswith("@"):
        path = Path(raw[1:])
        return path.read_text(encoding="utf-8")
    return raw


def _load_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not path.exists():
        return None, "missing"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return None, f"invalid_json: {exc}"
    if not isinstance(payload, dict):
        return None, "invalid_shape"
    return payload, None


def _node(
    node_id: str, node_type: str, status: str, metadata: dict[str, Any] | None = None
) -> dict[str, Any]:
    return {
        "id": node_id,
        "type": node_type,
        "status": status,
        "metadata": metadata or {},
    }


def _edge(
    source: str, target: str, relation: str, status: str = "observed"
) -> dict[str, str]:
    return {
        "source": source,
        "target": target,
        "relation": relation,
        "status": status,
    }


def main() -> int:
    args = _parse_args()
    args.report_file.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_file.parent.mkdir(parents=True, exist_ok=True)

    completeness_checks: list[dict[str, Any]] = []

    needs_source = "needs_json"
    needs_raw = _resolve_needs_json_arg(args.needs_json)
    if args.needs_file is not None:
        needs_source = str(args.needs_file)
        try:
            needs_raw = args.needs_file.read_text(encoding="utf-8-sig")
        except Exception as exc:
            needs_raw = "{}"
            completeness_checks.append(
                {
                    "check_id": "needs_file_read",
                    "passed": False,
                    "detail": f"path={args.needs_file}; error={exc}",
                }
            )

    try:
        needs = json.loads(needs_raw)
    except Exception as exc:
        needs = {}
        completeness_checks.append(
            {
                "check_id": "needs_json_parse",
                "passed": False,
                "detail": f"source={needs_source}; parse_error: {exc}",
            }
        )
    else:
        completeness_checks.append(
            {
                "check_id": "needs_json_parse",
                "passed": isinstance(needs, dict),
                "detail": "parsed" if isinstance(needs, dict) else "not_object",
            }
        )

    artifacts_dir = args.artifacts_dir
    required_job_results: dict[str, str] = {}

    required_jobs = [
        "pin_drift_guard",
        "smoke",
        "contracts",
        "registry_consistency",
        "openapi_verification",
        "runtime_canary",
        "dx_metrics",
        "ci_stability_trend",
    ]

    artifacts = {
        "smoke_report": artifacts_dir / "smoke_report.json",
        "runtime_coverage": artifacts_dir / "runtime_coverage.json",
        "skill_executability": artifacts_dir / "skill_executability.json",
        "policy_bundle_lifecycle": artifacts_dir
        / "policy_bundle_lifecycle_report.json",
        "promotion_readiness": artifacts_dir / "policy_promotion_readiness_report.json",
        "promotion_readiness_verify": artifacts_dir
        / "policy_promotion_readiness_verify_report.json",
        "dx_metrics_slo": artifacts_dir / "dx_metrics_slo_report.json",
        "critical_ci_trend": artifacts_dir / "critical_ci_trend_report.json",
        "critical_ci_trend_slo": artifacts_dir / "critical_ci_trend_slo_report.json",
        "runtime_exec_summary": artifacts_dir
        / "runtime_governance_executive_summary.json",
        "release_gate_report": artifacts_dir / "release_readiness_gate_report.json",
    }

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, str]] = []

    nodes.append(
        _node(
            "source.workflow.smoke_verification",
            "source",
            "active",
            {
                "workflow": ".github/workflows/smoke.yml",
                "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            },
        )
    )

    for job in required_jobs:
        item = needs.get(job) if isinstance(needs, dict) else None
        result = item.get("result") if isinstance(item, dict) else "unknown"
        required_job_results[job] = str(result)
        status = "passed" if result == "success" else "failed"
        nodes.append(_node(f"job.{job}", "job", status, {"result": result}))
        edges.append(
            _edge("source.workflow.smoke_verification", f"job.{job}", "triggers")
        )
        completeness_checks.append(
            {
                "check_id": f"job_present:{job}",
                "passed": isinstance(item, dict),
                "detail": f"result={result}",
            }
        )

    # The release readiness job generates lineage artifacts itself, so it is not
    # available inside the `needs` context. Model it explicitly to keep producer
    # edges valid without requiring an impossible self-reference in `needs`.
    nodes.append(
        _node(
            "job.release_readiness_gate",
            "job",
            "active",
            {"result": "self"},
        )
    )
    edges.append(
        _edge(
            "source.workflow.smoke_verification",
            "job.release_readiness_gate",
            "triggers",
        )
    )

    for key, path in artifacts.items():
        payload, error = _load_json(path)
        present = error is None
        status = "present" if present else "missing"
        metadata: dict[str, Any] = {"path": str(path)}
        if present:
            metadata["contract"] = payload.get("contract")
            metadata["status"] = payload.get("status") or payload.get("slo_status")
        else:
            metadata["error"] = error
        nodes.append(_node(f"artifact.{key}", "artifact", status, metadata))

        producer_job = "job.release_readiness_gate"
        if key in {"smoke_report"}:
            producer_job = "job.smoke"
        elif key in {
            "runtime_coverage",
            "skill_executability",
            "policy_bundle_lifecycle",
            "promotion_readiness",
            "promotion_readiness_verify",
            "runtime_exec_summary",
        }:
            producer_job = "job.runtime_canary"
        elif key in {"dx_metrics_slo"}:
            producer_job = "job.dx_metrics"
        elif key in {"critical_ci_trend", "critical_ci_trend_slo"}:
            producer_job = "job.ci_stability_trend"

        edges.append(
            _edge(
                producer_job,
                f"artifact.{key}",
                "produces",
                "observed" if present else "missing",
            )
        )
        completeness_checks.append(
            {
                "check_id": f"artifact_present:{key}",
                "passed": present,
                "detail": error or "present",
            }
        )

    nodes.append(
        _node(
            "decision.release_readiness",
            "decision",
            "unknown",
            {
                "source": "artifact.release_gate_report",
            },
        )
    )
    edges.append(
        _edge("artifact.release_gate_report", "decision.release_readiness", "drives")
    )

    gate_data, gate_error = _load_json(artifacts["release_gate_report"])
    if gate_error is None and gate_data is not None:
        decision = str(gate_data.get("decision", "unknown")).strip().lower()
        for node in nodes:
            if node.get("id") == "decision.release_readiness":
                node["status"] = decision or "unknown"
                node["metadata"]["gate_status"] = gate_data.get("status")
                break

    node_ids = [str(node.get("id", "")) for node in nodes]
    node_id_set = set(node_ids)
    completeness_checks.append(
        {
            "check_id": "node_ids_unique",
            "passed": len(node_ids) == len(node_id_set),
            "detail": f"count={len(node_ids)} unique={len(node_id_set)}",
        }
    )

    required_node_types = {"source", "job", "artifact", "decision"}
    observed_node_types = {str(node.get("type", "")).strip() for node in nodes}
    missing_node_types = sorted(required_node_types - observed_node_types)
    completeness_checks.append(
        {
            "check_id": "required_node_types_present",
            "passed": not missing_node_types,
            "detail": "present"
            if not missing_node_types
            else f"missing={missing_node_types}",
        }
    )

    missing_edge_refs: list[str] = []
    for edge in edges:
        source = str(edge.get("source", ""))
        target = str(edge.get("target", ""))
        if source not in node_id_set:
            missing_edge_refs.append(f"source:{source}")
        if target not in node_id_set:
            missing_edge_refs.append(f"target:{target}")
    completeness_checks.append(
        {
            "check_id": "edges_reference_existing_nodes",
            "passed": not missing_edge_refs,
            "detail": "ok"
            if not missing_edge_refs
            else f"missing_refs={missing_edge_refs[:10]}",
        }
    )

    if gate_error is None and gate_data is not None:
        gate_contract = gate_data.get("contract")
        gate_decision = str(gate_data.get("decision", "")).strip().lower()
        gate_status = str(gate_data.get("status", "")).strip().lower()
        completeness_checks.append(
            {
                "check_id": "release_gate_contract_expected",
                "passed": gate_contract == "release_readiness_gate_v1",
                "detail": f"contract={gate_contract}",
            }
        )
        completeness_checks.append(
            {
                "check_id": "release_gate_decision_known",
                "passed": gate_decision in {"go", "conditional-go", "no-go"},
                "detail": f"decision={gate_decision or 'unknown'}",
            }
        )
        completeness_checks.append(
            {
                "check_id": "release_gate_status_known",
                "passed": gate_status in {"passed", "failed"},
                "detail": f"status={gate_status or 'unknown'}",
            }
        )

    required_edges = [
        ("job.runtime_canary", "artifact.runtime_exec_summary"),
        ("job.ci_stability_trend", "artifact.critical_ci_trend_slo"),
        ("job.dx_metrics", "artifact.dx_metrics_slo"),
        ("artifact.release_gate_report", "decision.release_readiness"),
    ]

    for source, target in required_edges:
        exists = any(
            e.get("source") == source and e.get("target") == target for e in edges
        )
        completeness_checks.append(
            {
                "check_id": f"edge_present:{source}->{target}",
                "passed": exists,
                "detail": "present" if exists else "missing",
            }
        )

    passed = sum(1 for c in completeness_checks if c.get("passed"))
    total = len(completeness_checks)
    failed = total - passed

    node_type_counts: dict[str, int] = {}
    for node in nodes:
        node_type = str(node.get("type", "unknown"))
        node_type_counts[node_type] = node_type_counts.get(node_type, 0) + 1

    edge_relation_counts: dict[str, int] = {}
    for edge in edges:
        relation = str(edge.get("relation", "unknown"))
        edge_relation_counts[relation] = edge_relation_counts.get(relation, 0) + 1

    present_required_jobs = sum(
        1
        for job in required_jobs
        if isinstance(needs, dict) and isinstance(needs.get(job), dict)
    )

    provenance = {
        "schema_version": LINEAGE_SCHEMA_VERSION,
        "generator": "tooling/generate_release_lineage.py",
        "source_workflow": ".github/workflows/smoke.yml",
        "artifacts_dir": str(artifacts_dir),
        "required_jobs": {
            "total": len(required_jobs),
            "present_in_needs": present_required_jobs,
            "results": required_job_results,
        },
    }

    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "contract": LINEAGE_CONTRACT,
        "status": "passed" if failed == 0 else "failed",
        "provenance": provenance,
        "summary": {
            "total_checks": total,
            "passed_checks": passed,
            "failed_checks": failed,
            "nodes_total": len(nodes),
            "edges_total": len(edges),
            "node_type_counts": node_type_counts,
            "edge_relation_counts": edge_relation_counts,
        },
        "lineage": {
            "nodes": nodes,
            "edges": edges,
        },
        "completeness_checks": completeness_checks,
    }

    args.report_file.write_text(json.dumps(report, indent=2), encoding="utf-8")

    lines = [
        "## Release Lineage",
        "",
        f"- Contract: {report['contract']} (schema {LINEAGE_SCHEMA_VERSION})",
        f"- Status: {report['status']}",
        f"- Completeness checks: {passed}/{total}",
        f"- Nodes: {len(nodes)}",
        f"- Edges: {len(edges)}",
        "",
    ]

    if failed:
        lines.append("### Incomplete Checks")
        lines.append("")
        for check in completeness_checks:
            if not check.get("passed"):
                lines.append(f"- {check.get('check_id')}: {check.get('detail')}")
    else:
        lines.append("Lineage completeness checks passed.")

    lines.append("")
    args.markdown_file.write_text("\n".join(lines), encoding="utf-8")

    print("Release lineage")
    print(f"- status: {report['status']}")
    print(f"- completeness: {passed}/{total}")
    print(f"- report: {args.report_file}")
    print(f"- markdown: {args.markdown_file}")

    if args.fail_on_incomplete and failed:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

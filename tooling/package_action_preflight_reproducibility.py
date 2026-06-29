import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EVAL_MANIFEST = (
    ROOT / "docs" / "papers" / "action_preflight_forecast_study" / "BATCH_BF_EVALUATION_MANIFEST.json"
)
DEFAULT_OUT_ROOT = ROOT / "artifacts" / "paper_runs"


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _safe_hash(path: Path) -> str | None:
    try:
        if path.exists() and path.is_file():
            return _sha256(path)
    except Exception:
        return None
    return None


def _to_rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT)).replace("\\", "/")
    except Exception:
        return str(path).replace("\\", "/")


def _build_raw_reports_bundle(eval_manifest: dict[str, Any]) -> dict[str, Any]:
    references: list[str] = []

    # Batch B
    b = eval_manifest.get("batch_b_execution", {})
    references.extend(b.get("reports", []))

    # Batch C
    c = eval_manifest.get("batch_c_execution", {})
    if c.get("aggregate_report"):
        references.append(c["aggregate_report"])
    references.extend(c.get("variant_reports", []))

    # Batch D
    d = eval_manifest.get("batch_d_execution", {})
    if d.get("aggregate_report"):
        references.append(d["aggregate_report"])

    # Batch E
    e = eval_manifest.get("batch_e_execution", {})
    if e.get("aggregate_report"):
        references.append(e["aggregate_report"])

    unique_refs = []
    seen = set()
    for r in references:
        if r not in seen:
            unique_refs.append(r)
            seen.add(r)

    items = []
    for rel in unique_refs:
        p = ROOT / rel
        items.append(
            {
                "path": rel,
                "sha256": _safe_hash(p),
                "exists": bool(p.exists()),
            }
        )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(items),
        "items": items,
    }


def _build_frozen_inputs_hashes(eval_manifest: dict[str, Any]) -> dict[str, Any]:
    frozen = eval_manifest.get("frozen_inputs", {})
    items = {}
    for key in ["base_case_file", "base_batch_manifest", "runner"]:
        rel = frozen.get(key)
        if not rel:
            continue
        p = ROOT / rel
        items[key] = {
            "path": rel,
            "sha256": _safe_hash(p),
            "exists": bool(p.exists()),
        }

    protocol = ROOT / "docs" / "papers" / "action_preflight_forecast_study" / "BATCH_A_PROTOCOL.md"
    eval_path = ROOT / "docs" / "papers" / "action_preflight_forecast_study" / "BATCH_BF_EVALUATION_MANIFEST.json"
    items["protocol"] = {
        "path": _to_rel(protocol),
        "sha256": _safe_hash(protocol),
        "exists": bool(protocol.exists()),
    }
    items["evaluation_manifest"] = {
        "path": _to_rel(eval_path),
        "sha256": _safe_hash(eval_path),
        "exists": bool(eval_path.exists()),
    }

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "items": items,
    }


def _build_aggregated_tables_bundle(eval_manifest: dict[str, Any]) -> dict[str, Any]:
    # Batch B summary table
    batch_b_rows = []
    for rel in eval_manifest.get("batch_b_execution", {}).get("reports", []):
        p = ROOT / rel
        if not p.exists():
            continue
        data = _load_json(p)
        s = data.get("summary", {})
        batch_b_rows.append(
            {
                "batch_id": data.get("batch_id"),
                "batch_name": data.get("batch_name"),
                "pass_rate": s.get("pass_rate"),
                "errors": s.get("errors"),
                "fallback_ratio": s.get("fallback_ratio"),
                "unsafe_proceed_medium_high": s.get("unsafe_proceed_medium_high"),
                "go_no_go": data.get("go_no_go"),
            }
        )

    # Batch C deltas
    c_rel = eval_manifest.get("batch_c_execution", {}).get("aggregate_report")
    batch_c_deltas = {}
    if c_rel:
        p = ROOT / c_rel
        if p.exists():
            c = _load_json(p)
            batch_c_deltas = c.get("kpi_deltas_vs_full_skill", {})

    # Batch D summary
    d_rel = eval_manifest.get("batch_d_execution", {}).get("aggregate_report")
    batch_d_summary = {}
    batch_d_by_perturbation = {}
    if d_rel:
        p = ROOT / d_rel
        if p.exists():
            d = _load_json(p)
            batch_d_summary = d.get("summary", {})
            batch_d_by_perturbation = d.get("by_perturbation", {})

    # Batch E summary
    e_rel = eval_manifest.get("batch_e_execution", {}).get("aggregate_report")
    batch_e_summary = {}
    batch_e_strata = {}
    if e_rel:
        p = ROOT / e_rel
        if p.exists():
            e = _load_json(p)
            batch_e_summary = e.get("summary", {})
            batch_e_strata = e.get("strata", {})

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tables": {
            "batch_b_core_benchmark": batch_b_rows,
            "batch_c_ablation_deltas": batch_c_deltas,
            "batch_d_robustness_summary": batch_d_summary,
            "batch_d_by_perturbation": batch_d_by_perturbation,
            "batch_e_calibration_summary": batch_e_summary,
            "batch_e_strata": batch_e_strata,
        },
    }


def _build_figure_specs(eval_manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "figures": [
            {
                "id": "fig_b_core_kpis",
                "title": "Batch B Core KPIs by Batch",
                "source": "aggregated_tables_bundle.json::tables.batch_b_core_benchmark",
                "chart": "bar",
                "x": "batch_name",
                "y": ["pass_rate", "fallback_ratio"],
            },
            {
                "id": "fig_c_ablation_deltas",
                "title": "Batch C Ablation Delta Pass Rate vs Full Skill",
                "source": "aggregated_tables_bundle.json::tables.batch_c_ablation_deltas",
                "chart": "heatmap",
                "x": "variant",
                "y": "batch_id",
                "value": "delta_pass_rate",
            },
            {
                "id": "fig_d_perturbation_resilience",
                "title": "Batch D Pass Rate by Perturbation",
                "source": "aggregated_tables_bundle.json::tables.batch_d_by_perturbation",
                "chart": "bar",
                "x": "perturbation",
                "y": "pass_rate",
            },
            {
                "id": "fig_e_reliability_curve",
                "title": "Batch E Reliability Curve",
                "source": "aggregated_tables_bundle.json::tables.batch_e_calibration_summary.reliability_curve_bins",
                "chart": "line",
                "x": "avg_confidence",
                "y": "empirical_accuracy",
            },
        ],
        "notes": [
            "All figure sources are derived from frozen run artifacts only.",
            "No post-hoc threshold tuning is applied in this package.",
        ],
        "status": "ready",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Package Batch F reproducibility bundle for action preflight study.")
    parser.add_argument("--eval-manifest", default=str(DEFAULT_EVAL_MANIFEST))
    parser.add_argument("--run-label", default="reproducibility_run1")
    args = parser.parse_args()

    eval_manifest = _load_json(Path(args.eval_manifest))

    out_dir = DEFAULT_OUT_ROOT / f"F_{args.run_label}"
    out_dir.mkdir(parents=True, exist_ok=True)

    run_manifest_src = DEFAULT_OUT_ROOT / f"F_{args.run_label}_run_manifest.json"
    run_manifest_out = out_dir / "run_manifest.json"
    if run_manifest_src.exists():
        run_manifest_out.write_text(run_manifest_src.read_text(encoding="utf-8"), encoding="utf-8")
    else:
        run_manifest_out.write_text(
            json.dumps(
                {
                    "status": "missing",
                    "message": "Expected F run manifest not found. Generate with prepare_paper_run_manifest.py",
                    "expected": _to_rel(run_manifest_src),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    frozen_inputs_hashes = _build_frozen_inputs_hashes(eval_manifest)
    raw_reports_bundle = _build_raw_reports_bundle(eval_manifest)
    aggregated_tables_bundle = _build_aggregated_tables_bundle(eval_manifest)
    figure_specs = _build_figure_specs(eval_manifest)

    (out_dir / "frozen_inputs_hashes.json").write_text(
        json.dumps(frozen_inputs_hashes, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out_dir / "raw_reports_bundle.json").write_text(
        json.dumps(raw_reports_bundle, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out_dir / "aggregated_tables_bundle.json").write_text(
        json.dumps(aggregated_tables_bundle, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out_dir / "figure_specs.json").write_text(
        json.dumps(figure_specs, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    package_index = {
        "study_id": eval_manifest.get("study_id"),
        "batch_label": "F",
        "run_label": args.run_label,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "package_dir": _to_rel(out_dir),
        "files": {
            "run_manifest": _to_rel(out_dir / "run_manifest.json"),
            "frozen_inputs_hashes": _to_rel(out_dir / "frozen_inputs_hashes.json"),
            "raw_reports_bundle": _to_rel(out_dir / "raw_reports_bundle.json"),
            "aggregated_tables_bundle": _to_rel(out_dir / "aggregated_tables_bundle.json"),
            "figure_specs": _to_rel(out_dir / "figure_specs.json"),
        },
    }
    (out_dir / "package_index.json").write_text(
        json.dumps(package_index, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(json.dumps({"status": "ok", "package_dir": str(out_dir)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

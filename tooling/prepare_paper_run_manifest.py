import argparse
import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROTOCOL = ROOT / "docs" / "papers" / "action_preflight_forecast_study" / "BATCH_A_PROTOCOL.md"
DEFAULT_EVAL_MANIFEST = ROOT / "docs" / "papers" / "action_preflight_forecast_study" / "BATCH_BF_EVALUATION_MANIFEST.json"
DEFAULT_BATCH_MANIFEST = ROOT / "tooling" / "action_preflight_batches_manifest.json"
DEFAULT_CASE_FILE = ROOT / "test_inputs" / "action_preflight_batch_cases.json"
DEFAULT_RUNNER = ROOT / "tooling" / "run_action_preflight_batches.py"
DEFAULT_OUTDIR = ROOT / "artifacts" / "paper_runs"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _git_rev(path: Path) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return proc.stdout.strip()
    except Exception:
        return None


def _safe_exists(path: Path) -> bool:
    try:
        return path.exists()
    except Exception:
        return False


def build_manifest(study_id: str, batch_label: str, run_label: str) -> dict:
    registry_root = ROOT.parent / "agent-skill-registry"

    files = {
        "protocol": DEFAULT_PROTOCOL,
        "eval_manifest": DEFAULT_EVAL_MANIFEST,
        "batch_manifest": DEFAULT_BATCH_MANIFEST,
        "case_file": DEFAULT_CASE_FILE,
        "runner": DEFAULT_RUNNER,
    }

    file_hashes = {}
    for key, path in files.items():
        if _safe_exists(path):
            file_hashes[key] = {
                "path": str(path),
                "sha256": _sha256(path),
            }
        else:
            file_hashes[key] = {
                "path": str(path),
                "sha256": None,
            }

    return {
        "study_id": study_id,
        "batch_label": batch_label,
        "run_label": run_label,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "workspace": {
            "agent_skills_root": str(ROOT),
            "agent_skill_registry_root": str(registry_root),
        },
        "commits": {
            "agent_skills": _git_rev(ROOT),
            "agent_skill_registry": _git_rev(registry_root) if _safe_exists(registry_root) else None,
        },
        "file_hashes": file_hashes,
        "environment": {
            "python_version": sys.version,
            "python_executable": sys.executable,
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor(),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare paper-grade run manifest for reproducible evidence.")
    parser.add_argument("--study-id", default="action_preflight_forecast_journal_2026")
    parser.add_argument("--batch-label", required=True)
    parser.add_argument("--run-label", required=True)
    parser.add_argument("--outdir", default=str(DEFAULT_OUTDIR))
    args = parser.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    manifest = build_manifest(args.study_id, args.batch_label, args.run_label)
    out_path = outdir / f"{args.batch_label}_{args.run_label}_run_manifest.json"
    out_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({"status": "ok", "manifest": str(out_path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

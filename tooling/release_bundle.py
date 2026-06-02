from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


RELEASE_BUNDLE_CONTRACT = "release_bundle_v1"
DEPLOYMENT_STATE_CONTRACT = "deployment_state_v1"

RUNTIME_INCLUDE_PATHS = [
    "bindings",
    "cli",
    "customer_facing",
    "gateway",
    "official_services",
    "policies",
    "runtime",
    "tooling",
    "pyproject.toml",
    "requirements-lock.txt",
    "README.md",
    "docs/specs/consumer_facing_v1_openapi.json",
]

REGISTRY_INCLUDE_PATHS = [
    "capabilities",
    "catalog",
    "skills",
    "vocabulary",
    "README.md",
]

EVIDENCE_PATHS = [
    "release_readiness_gate_report.json",
    "release_readiness_gate_summary.md",
    "release_lineage.json",
    "release_lineage.md",
    "release_lineage_contract_report.json",
    "runtime_governance_executive_summary.json",
    "policy_promotion_readiness_report.json",
    "policy_promotion_readiness_verify_report.json",
]

REQUIRED_EVIDENCE = {
    "release_readiness_gate_report.json",
    "release_lineage.json",
    "release_lineage_contract_report.json",
}


@dataclass
class ReleaseBundleBuildResult:
    bundle_id: str
    bundle_root: Path
    manifest_path: Path
    included_files: int
    included_evidence: list[str]


@dataclass
class ReleaseBundleVerifyResult:
    ok: bool
    bundle_id: str | None
    errors: list[str]
    warnings: list[str]
    verified_files: int


@dataclass
class ReleaseBundlePromoteResult:
    environment: str
    bundle_id: str
    release_root: Path
    current_pointer: Path
    previous_bundle_id: str | None


@dataclass
class ReleaseBundleRollbackResult:
    environment: str
    bundle_id: str
    previous_bundle_id: str | None
    current_pointer: Path


def _copy_path(src: Path, dst: Path) -> int:
    if src.is_dir():
        shutil.copytree(src, dst, dirs_exist_ok=True)
        return sum(1 for p in dst.rglob("*") if p.is_file())
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return 1


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _collect_checksums(root: Path) -> dict[str, str]:
    checksums: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            rel = path.relative_to(root).as_posix()
            checksums[rel] = _sha256_file(path)
    return checksums


def _git_metadata(repo_root: Path) -> dict[str, Any]:
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        commit = None

    try:
        dirty = bool(
            subprocess.check_output(
                ["git", "status", "--porcelain"],
                cwd=repo_root,
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
        )
    except Exception:
        dirty = None

    return {"commit": commit, "dirty": dirty}


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_evidence_path(artifacts_dir: Path, name: str) -> Path | None:
    preferred = artifacts_dir / name
    if preferred.exists():
        return preferred

    path = Path(name)
    stem = path.stem
    suffix = path.suffix
    candidates = sorted(artifacts_dir.glob(f"{stem}.*{suffix}"), reverse=True)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def build_release_bundle(
    *,
    runtime_root: Path,
    registry_root: Path,
    artifacts_dir: Path,
    out_root: Path,
    bundle_label: str = "candidate",
) -> ReleaseBundleBuildResult:
    out_root.mkdir(parents=True, exist_ok=True)

    timestamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    runtime_git = _git_metadata(runtime_root)
    registry_git = _git_metadata(registry_root)
    runtime_short = str(runtime_git.get("commit") or "nogit")[:8]
    bundle_id = f"{bundle_label}-{timestamp}-{runtime_short}"
    bundle_root = out_root / bundle_id
    payload_runtime_root = bundle_root / "payload" / "runtime"
    payload_registry_root = bundle_root / "payload" / "registry"
    evidence_root = bundle_root / "evidence"

    if bundle_root.exists():
        shutil.rmtree(bundle_root)

    included_files = 0
    for rel in RUNTIME_INCLUDE_PATHS:
        src = runtime_root / rel
        if not src.exists():
            continue
        included_files += _copy_path(src, payload_runtime_root / rel)

    for rel in REGISTRY_INCLUDE_PATHS:
        src = registry_root / rel
        if not src.exists():
            continue
        included_files += _copy_path(src, payload_registry_root / rel)

    included_evidence: list[str] = []
    for name in EVIDENCE_PATHS:
        src = _resolve_evidence_path(artifacts_dir, name)
        if src is None:
            continue
        included_files += _copy_path(src, evidence_root / name)
        included_evidence.append(name)

    runtime_checksums = _collect_checksums(payload_runtime_root)
    registry_checksums = _collect_checksums(payload_registry_root)
    evidence_checksums = _collect_checksums(evidence_root) if evidence_root.exists() else {}

    manifest = {
        "contract": RELEASE_BUNDLE_CONTRACT,
        "bundle_id": bundle_id,
        "bundle_label": bundle_label,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": {
            "runtime_root": str(runtime_root),
            "registry_root": str(registry_root),
            "runtime_git": runtime_git,
            "registry_git": registry_git,
        },
        "payload": {
            "runtime_root": "payload/runtime",
            "registry_root": "payload/registry",
            "runtime_checksums": runtime_checksums,
            "registry_checksums": registry_checksums,
        },
        "evidence": {
            "root": "evidence",
            "files": included_evidence,
            "required": sorted(REQUIRED_EVIDENCE),
            "checksums": evidence_checksums,
        },
        "summary": {
            "included_files": included_files,
            "runtime_files": len(runtime_checksums),
            "registry_files": len(registry_checksums),
            "evidence_files": len(evidence_checksums),
        },
    }

    manifest_path = bundle_root / "bundle_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    return ReleaseBundleBuildResult(
        bundle_id=bundle_id,
        bundle_root=bundle_root,
        manifest_path=manifest_path,
        included_files=included_files,
        included_evidence=included_evidence,
    )


def verify_release_bundle(*, bundle_root: Path) -> ReleaseBundleVerifyResult:
    errors: list[str] = []
    warnings: list[str] = []
    verified_files = 0

    manifest_path = bundle_root / "bundle_manifest.json"
    if not manifest_path.exists():
        return ReleaseBundleVerifyResult(
            ok=False,
            bundle_id=None,
            errors=[f"Missing manifest: {manifest_path}"],
            warnings=[],
            verified_files=0,
        )

    try:
        manifest = _read_json(manifest_path)
    except Exception as exc:
        return ReleaseBundleVerifyResult(
            ok=False,
            bundle_id=None,
            errors=[f"Invalid manifest JSON: {exc}"],
            warnings=[],
            verified_files=0,
        )

    bundle_id = manifest.get("bundle_id") if isinstance(manifest, dict) else None
    if manifest.get("contract") != RELEASE_BUNDLE_CONTRACT:
        errors.append(f"Unexpected contract: {manifest.get('contract')}")

    payload = manifest.get("payload") if isinstance(manifest.get("payload"), dict) else {}
    evidence = manifest.get("evidence") if isinstance(manifest.get("evidence"), dict) else {}

    def _verify_section(root_rel: str, checksums: dict[str, Any], label: str) -> None:
        nonlocal verified_files
        base = bundle_root / root_rel
        if not base.exists():
            errors.append(f"Missing {label} root: {base}")
            return
        for rel, expected in checksums.items():
            path = base / rel
            if not path.exists():
                errors.append(f"Missing {label} file: {root_rel}/{rel}")
                continue
            actual = _sha256_file(path)
            if actual != expected:
                errors.append(f"Checksum mismatch for {root_rel}/{rel}")
                continue
            verified_files += 1

    _verify_section(
        str(payload.get("runtime_root") or "payload/runtime"),
        payload.get("runtime_checksums") if isinstance(payload.get("runtime_checksums"), dict) else {},
        "runtime payload",
    )
    _verify_section(
        str(payload.get("registry_root") or "payload/registry"),
        payload.get("registry_checksums") if isinstance(payload.get("registry_checksums"), dict) else {},
        "registry payload",
    )
    _verify_section(
        str(evidence.get("root") or "evidence"),
        evidence.get("checksums") if isinstance(evidence.get("checksums"), dict) else {},
        "evidence",
    )

    evidence_root = bundle_root / str(evidence.get("root") or "evidence")
    required = evidence.get("required") if isinstance(evidence.get("required"), list) else []
    for name in required:
        if not (evidence_root / str(name)).exists():
            errors.append(f"Missing required evidence file: {name}")

    if not isinstance(bundle_id, str) or not bundle_id:
        errors.append("Manifest bundle_id missing or invalid")

    return ReleaseBundleVerifyResult(
        ok=len(errors) == 0,
        bundle_id=bundle_id if isinstance(bundle_id, str) else None,
        errors=errors,
        warnings=warnings,
        verified_files=verified_files,
    )


def _deployment_paths(deployment_root: Path, environment: str) -> tuple[Path, Path, Path]:
    env_root = deployment_root / environment
    releases_root = env_root / "releases"
    current_path = env_root / "current.json"
    history_path = env_root / "history.jsonl"
    releases_root.mkdir(parents=True, exist_ok=True)
    return releases_root, current_path, history_path


def _read_current_pointer(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = _read_json(path)
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def promote_release_bundle(
    *,
    bundle_root: Path,
    deployment_root: Path,
    environment: str,
) -> ReleaseBundlePromoteResult:
    verify = verify_release_bundle(bundle_root=bundle_root)
    if not verify.ok or not verify.bundle_id:
        raise ValueError(f"Bundle verification failed: {verify.errors}")

    releases_root, current_path, history_path = _deployment_paths(
        deployment_root, environment
    )
    existing = _read_current_pointer(current_path)
    previous_bundle_id = (
        existing.get("bundle_id") if isinstance(existing, dict) else None
    )

    release_root = releases_root / verify.bundle_id
    if release_root.exists():
        shutil.rmtree(release_root)
    shutil.copytree(bundle_root, release_root)

    pointer = {
        "contract": DEPLOYMENT_STATE_CONTRACT,
        "environment": environment,
        "bundle_id": verify.bundle_id,
        "bundle_root": str(release_root),
        "promoted_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "previous_bundle_id": previous_bundle_id,
    }
    current_path.write_text(json.dumps(pointer, indent=2), encoding="utf-8")
    with history_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"event": "promote", **pointer}) + "\n")

    return ReleaseBundlePromoteResult(
        environment=environment,
        bundle_id=verify.bundle_id,
        release_root=release_root,
        current_pointer=current_path,
        previous_bundle_id=previous_bundle_id if isinstance(previous_bundle_id, str) else None,
    )


def rollback_release_bundle(
    *,
    deployment_root: Path,
    environment: str,
    target_bundle_id: str | None = None,
) -> ReleaseBundleRollbackResult:
    releases_root, current_path, history_path = _deployment_paths(
        deployment_root, environment
    )
    current = _read_current_pointer(current_path)
    if current is None:
        raise ValueError(f"No current deployment pointer for environment '{environment}'")

    current_bundle_id = current.get("bundle_id")
    if not isinstance(current_bundle_id, str) or not current_bundle_id:
        raise ValueError("Current deployment pointer is missing bundle_id")

    if target_bundle_id is None:
        releases = sorted(
            [p.name for p in releases_root.iterdir() if p.is_dir() and p.name != current_bundle_id]
        )
        if not releases:
            raise ValueError(f"No previous release available for environment '{environment}'")
        target_bundle_id = releases[-1]

    target_root = releases_root / target_bundle_id
    if not target_root.exists():
        raise ValueError(f"Target release does not exist: {target_root}")

    verify = verify_release_bundle(bundle_root=target_root)
    if not verify.ok:
        raise ValueError(f"Target bundle verification failed: {verify.errors}")

    pointer = {
        "contract": DEPLOYMENT_STATE_CONTRACT,
        "environment": environment,
        "bundle_id": target_bundle_id,
        "bundle_root": str(target_root),
        "promoted_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "previous_bundle_id": current_bundle_id,
        "rollback": True,
    }
    current_path.write_text(json.dumps(pointer, indent=2), encoding="utf-8")
    with history_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"event": "rollback", **pointer}) + "\n")

    return ReleaseBundleRollbackResult(
        environment=environment,
        bundle_id=target_bundle_id,
        previous_bundle_id=current_bundle_id,
        current_pointer=current_path,
    )
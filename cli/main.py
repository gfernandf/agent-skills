from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from customization.binding_activation import BindingActivationService
from customization.binding_state_store import BindingStateStore
from customization.override_intent_loader import OverrideIntentLoader
from customization.quality_gate import QualityGate
from customization.service_descriptor_loader import ServiceDescriptorLoader

from runtime.binding_registry import BindingRegistry
from runtime.audit import AuditRecorder
from runtime.capability_loader import YamlCapabilityLoader
from runtime.execution_engine import ExecutionEngine
from runtime.skill_loader import YamlSkillLoader

from runtime.engine_factory import build_runtime_components
from runtime.models import ExecutionOptions, ExecutionRequest
from gateway.core import SkillGateway
from tooling.promotion_package import (
    prepare_promotion_package,
    validate_promotion_package,
)


def main() -> None:

    parser = argparse.ArgumentParser(prog="skills")
    sub = parser.add_subparsers(dest="command", required=True)

    # Common arguments for roots
    def add_root_args(cmd_parser):
        cmd_parser.add_argument(
            "--registry-root",
            type=Path,
            default=None,
            help="Path to the registry root directory",
        )
        cmd_parser.add_argument(
            "--runtime-root",
            type=Path,
            default=None,
            help="Path to the runtime root directory",
        )
        cmd_parser.add_argument(
            "--host-root",
            type=Path,
            default=None,
            help="Path to the host root directory",
        )
        cmd_parser.add_argument(
            "--local-skills-root",
            type=Path,
            default=None,
            help=(
                "Path to a local skills directory containing user-defined workflows. "
                "Defaults to <runtime-root>/skills/local if the directory exists. "
                "Skills here take resolution priority over the shared registry."
            ),
        )

    run_cmd = sub.add_parser("run", help="Execute a skill")
    run_cmd.add_argument("skill_id")
    run_cmd.add_argument("--input", default=None)
    run_cmd.add_argument("--input-file", default=None)
    run_cmd.add_argument(
        "--trace-id", default=None, help="Optional trace id for correlation"
    )
    run_cmd.add_argument(
        "--required-conformance-profile",
        choices=["strict", "standard", "experimental"],
        default=None,
        help="Optional minimum conformance profile for all capabilities executed by this run.",
    )
    run_cmd.add_argument(
        "--audit-mode",
        choices=["off", "standard", "full"],
        default=None,
        help="Audit record mode for this run. Defaults to runtime configuration.",
    )
    add_root_args(run_cmd)

    describe_cmd = sub.add_parser("describe", help="Describe a skill")
    describe_cmd.add_argument("skill_id")
    add_root_args(describe_cmd)

    discover_cmd = sub.add_parser("discover", help="Discover skills for an intent")
    discover_cmd.add_argument("intent", help="Natural language intent used for ranking")
    discover_cmd.add_argument("--domain", default=None, help="Optional domain filter")
    discover_cmd.add_argument(
        "--role",
        default=None,
        choices=["procedure", "utility", "sidecar"],
        help="Optional role filter",
    )
    discover_cmd.add_argument(
        "--limit", type=int, default=10, help="Max results to return"
    )
    discover_cmd.add_argument(
        "--json", action="store_true", help="Emit machine-readable JSON output"
    )
    add_root_args(discover_cmd)

    list_cmd = sub.add_parser("list", help="List skills with optional filters")
    list_cmd.add_argument("--domain", default=None, help="Filter by domain")
    list_cmd.add_argument(
        "--role",
        default=None,
        choices=["procedure", "utility", "sidecar"],
        help="Filter by classification role",
    )
    list_cmd.add_argument("--status", default=None, help="Filter by metadata status")
    list_cmd.add_argument(
        "--invocation",
        default=None,
        choices=["direct", "attach", "both"],
        help="Filter by classification invocation",
    )
    list_cmd.add_argument(
        "--json", action="store_true", help="Emit machine-readable JSON output"
    )
    add_root_args(list_cmd)

    attach_cmd = sub.add_parser(
        "attach", help="Attach a skill to an existing target and execute"
    )
    attach_cmd.add_argument("skill_id", help="Skill id to attach")
    attach_cmd.add_argument(
        "--target-type",
        required=True,
        choices=["task", "run", "output", "transcript", "artifact"],
        help="Attach target type",
    )
    attach_cmd.add_argument(
        "--target-ref", required=True, help="Opaque reference to target instance"
    )
    attach_cmd.add_argument(
        "--input", default=None, help="Inline JSON object for skill inputs"
    )
    attach_cmd.add_argument(
        "--input-file", default=None, help="Path to JSON file with skill inputs"
    )
    attach_cmd.add_argument(
        "--trace-id", default=None, help="Optional trace id for correlation"
    )
    attach_cmd.add_argument(
        "--include-trace", action="store_true", help="Include execution event trace"
    )
    attach_cmd.add_argument(
        "--required-conformance-profile",
        choices=["strict", "standard", "experimental"],
        default=None,
        help="Optional minimum conformance profile for all capabilities executed by this run.",
    )
    attach_cmd.add_argument(
        "--audit-mode",
        choices=["off", "standard", "full"],
        default=None,
        help="Audit record mode for this run. Defaults to runtime configuration.",
    )
    attach_cmd.add_argument(
        "--json", action="store_true", help="Emit machine-readable JSON output"
    )
    add_root_args(attach_cmd)

    gateway_diag_cmd = sub.add_parser(
        "gateway-diagnostics", help="Show gateway cache diagnostics"
    )
    gateway_diag_cmd.add_argument(
        "--json", action="store_true", help="Emit machine-readable JSON output"
    )
    add_root_args(gateway_diag_cmd)

    gateway_reset_cmd = sub.add_parser(
        "gateway-reset-metrics", help="Reset gateway diagnostics metrics"
    )
    gateway_reset_cmd.add_argument(
        "--clear-cache",
        action="store_true",
        help="Also clear in-memory gateway caches when resetting metrics.",
    )
    gateway_reset_cmd.add_argument(
        "--json", action="store_true", help="Emit machine-readable JSON output"
    )
    add_root_args(gateway_reset_cmd)

    activate_cmd = sub.add_parser("activate", help="Apply override activation")
    activate_cmd.add_argument("--capability", default=None)
    add_root_args(activate_cmd)

    trace_cmd = sub.add_parser("trace", help="Execute a skill with detailed tracing")
    trace_cmd.add_argument("skill_id")
    trace_cmd.add_argument("--input", default=None)
    trace_cmd.add_argument("--input-file", default=None)
    trace_cmd.add_argument(
        "--trace-id", default=None, help="Optional trace id for correlation"
    )
    trace_cmd.add_argument(
        "--required-conformance-profile",
        choices=["strict", "standard", "experimental"],
        default=None,
        help="Optional minimum conformance profile for all capabilities executed by this run.",
    )
    trace_cmd.add_argument(
        "--audit-mode",
        choices=["off", "standard", "full"],
        default=None,
        help="Audit record mode for this run. Defaults to runtime configuration.",
    )
    add_root_args(trace_cmd)

    audit_purge_cmd = sub.add_parser(
        "audit-purge", help="Purge persisted skill execution audit records"
    )
    audit_purge_cmd.add_argument("--trace-id", default=None)
    audit_purge_cmd.add_argument("--skill-id", default=None)
    audit_purge_cmd.add_argument("--older-than-days", type=int, default=None)
    audit_purge_cmd.add_argument(
        "--all", action="store_true", help="Delete all persisted audit records"
    )
    add_root_args(audit_purge_cmd)

    explain_cap_cmd = sub.add_parser(
        "explain-capability",
        help="Explain effective binding resolution and conformance chain",
    )
    explain_cap_cmd.add_argument("capability_id")
    explain_cap_cmd.add_argument(
        "--required-conformance-profile",
        choices=["strict", "standard", "experimental"],
        default=None,
        help="Optional minimum conformance profile used for eligibility planning.",
    )
    add_root_args(explain_cap_cmd)

    gov_cmd = sub.add_parser(
        "skill-governance",
        help="List skill governance entries from operational quality catalog",
    )
    gov_cmd.add_argument(
        "--min-state",
        default=None,
        choices=["draft", "validated", "lab-verified", "trusted", "recommended"],
    )
    gov_cmd.add_argument("--limit", type=int, default=20)
    add_root_args(gov_cmd)

    doctor_cmd = sub.add_parser("doctor", help="Run system health checks")
    add_root_args(doctor_cmd)

    scaffold_cmd = sub.add_parser(
        "scaffold",
        help="Generate a skill YAML from a natural-language intent description",
    )
    scaffold_cmd.add_argument(
        "intent",
        help="Plain-language description of the workflow to create.",
    )
    scaffold_cmd.add_argument(
        "--channel",
        choices=["local", "experimental", "community"],
        default="local",
        help="Target skill channel (default: local).",
    )
    scaffold_cmd.add_argument(
        "--model",
        default="gpt-4o-mini",
        help="OpenAI model to use when OPENAI_API_KEY is set (default: gpt-4o-mini).",
    )
    scaffold_cmd.add_argument(
        "--dry-run",
        action="store_true",
        help="Print generated YAML to stdout without writing any file.",
    )
    scaffold_cmd.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Override output directory. Defaults to <local-skills-root>/<domain>/<slug>/.",
    )
    add_root_args(scaffold_cmd)

    package_prepare_cmd = sub.add_parser(
        "package-prepare",
        help="Prepare a registry promotion package from a local skill",
    )
    package_prepare_target = package_prepare_cmd.add_mutually_exclusive_group(
        required=True
    )
    package_prepare_target.add_argument(
        "--skill-id", default=None, help="Skill ID to package (domain.slug)."
    )
    package_prepare_target.add_argument(
        "--skill-file",
        type=Path,
        default=None,
        help="Explicit path to local skill.yaml to package.",
    )
    package_prepare_cmd.add_argument(
        "--target-channel",
        choices=["experimental", "community", "official"],
        default="experimental",
        help="Target registry channel for the package (official is typically maintainer-led).",
    )
    package_prepare_cmd.add_argument(
        "--out-root",
        type=Path,
        default=None,
        help=(
            "Package output root. Defaults to <runtime-root>/artifacts/promotion_packages/ "
            "(falls back to legacy officialization_packages if it already exists)."
        ),
    )
    package_prepare_cmd.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON output.",
    )
    add_root_args(package_prepare_cmd)

    package_validate_cmd = sub.add_parser(
        "package-validate",
        help="Validate a prepared promotion package",
    )
    package_validate_cmd.add_argument(
        "package_path",
        type=Path,
        help="Path to package directory produced by package-prepare.",
    )
    package_validate_cmd.add_argument(
        "--print-pr-command",
        action="store_true",
        help="Print suggested git/gh commands to create a PR when package is valid.",
    )
    package_validate_cmd.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON output.",
    )
    add_root_args(package_validate_cmd)

    package_pr_cmd = sub.add_parser(
        "package-pr",
        help="Create a registry PR from a validated promotion package",
    )
    package_pr_cmd.add_argument(
        "package_path",
        type=Path,
        help="Path to package directory produced by package-prepare.",
    )
    package_pr_cmd.add_argument(
        "--registry-repo-root",
        type=Path,
        default=None,
        help="Path to local agent-skill-registry git repo (defaults to --registry-root).",
    )
    package_pr_cmd.add_argument(
        "--remote",
        default="origin",
        help="Git remote name to push branch to (default: origin).",
    )
    package_pr_cmd.add_argument(
        "--base",
        default="main",
        help="Base branch for PR creation (default: main).",
    )
    package_pr_cmd.add_argument(
        "--draft",
        action="store_true",
        help="Create PR as draft.",
    )
    package_pr_cmd.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned operations but do not run git/gh commands.",
    )
    package_pr_cmd.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON output.",
    )
    add_root_args(package_pr_cmd)

    openapi_cmd = sub.add_parser(
        "openapi", help="Run OpenAPI verification and diagnostics"
    )
    openapi_sub = openapi_cmd.add_subparsers(dest="openapi_command", required=True)

    openapi_verify_bindings_cmd = openapi_sub.add_parser(
        "verify-bindings",
        help="Run OpenAPI binding scenarios",
    )
    openapi_verify_bindings_cmd.add_argument("--scenario", type=Path, default=None)
    openapi_verify_bindings_cmd.add_argument("--all", action="store_true")
    openapi_verify_bindings_cmd.add_argument("--scenarios-dir", type=Path, default=None)
    openapi_verify_bindings_cmd.add_argument("--report-file", type=Path, default=None)
    add_root_args(openapi_verify_bindings_cmd)

    openapi_verify_invoker_cmd = openapi_sub.add_parser(
        "verify-invoker",
        help="Run runtime-level OpenAPI invoker checks",
    )
    add_root_args(openapi_verify_invoker_cmd)

    openapi_verify_errors_cmd = openapi_sub.add_parser(
        "verify-errors",
        help="Run OpenAPI error contract checks",
    )
    add_root_args(openapi_verify_errors_cmd)

    serve_cmd = sub.add_parser("serve", help="Start the HTTP API server")
    serve_cmd.add_argument(
        "--host",
        default=None,
        help="Bind address (default: 127.0.0.1 or AGENT_SKILLS_HOST)",
    )
    serve_cmd.add_argument(
        "--port",
        type=int,
        default=None,
        help="Bind port (default: 8080 or AGENT_SKILLS_PORT)",
    )
    serve_cmd.add_argument(
        "--api-key",
        default=None,
        help="API key for auth (default: AGENT_SKILLS_API_KEY)",
    )
    serve_cmd.add_argument(
        "--cors-origins", default=None, help="Comma-separated CORS origins"
    )
    add_root_args(serve_cmd)

    args = parser.parse_args()

    # Resolve roots with defaults
    runtime_root = args.runtime_root or Path.cwd()
    registry_root = args.registry_root or (runtime_root.parent / "agent-skill-registry")
    host_root = args.host_root or runtime_root
    local_skills_root = getattr(args, "local_skills_root", None)

    if args.command == "run":
        _cmd_run(
            registry_root,
            runtime_root,
            host_root,
            args.skill_id,
            args.input,
            args.input_file,
            args.trace_id,
            args.required_conformance_profile,
            args.audit_mode,
            local_skills_root,
        )

    elif args.command == "describe":
        _cmd_describe(registry_root, args.skill_id)

    elif args.command == "discover":
        _cmd_discover(
            registry_root,
            runtime_root,
            host_root,
            args.intent,
            args.domain,
            args.role,
            args.limit,
            args.json,
            local_skills_root,
        )

    elif args.command == "list":
        _cmd_list_skills(
            registry_root,
            runtime_root,
            host_root,
            args.domain,
            args.role,
            args.status,
            args.invocation,
            args.json,
            local_skills_root,
        )

    elif args.command == "attach":
        _cmd_attach(
            registry_root,
            runtime_root,
            host_root,
            args.skill_id,
            args.target_type,
            args.target_ref,
            args.input,
            args.input_file,
            args.trace_id,
            args.include_trace,
            args.required_conformance_profile,
            args.audit_mode,
            args.json,
            local_skills_root,
        )

    elif args.command == "gateway-diagnostics":
        _cmd_gateway_diagnostics(
            registry_root,
            runtime_root,
            host_root,
            args.json,
            local_skills_root,
        )

    elif args.command == "gateway-reset-metrics":
        _cmd_gateway_reset_metrics(
            registry_root,
            runtime_root,
            host_root,
            args.clear_cache,
            args.json,
            local_skills_root,
        )

    elif args.command == "activate":
        _cmd_activate(runtime_root, host_root, args.capability)

    elif args.command == "trace":
        _cmd_trace(
            registry_root,
            runtime_root,
            host_root,
            args.skill_id,
            args.input,
            args.input_file,
            args.trace_id,
            args.required_conformance_profile,
            args.audit_mode,
            local_skills_root,
        )

    elif args.command == "explain-capability":
        _cmd_explain_capability(
            registry_root,
            runtime_root,
            host_root,
            args.capability_id,
            args.required_conformance_profile,
        )

    elif args.command == "skill-governance":
        _cmd_skill_governance(
            registry_root,
            runtime_root,
            host_root,
            args.min_state,
            args.limit,
        )

    elif args.command == "doctor":
        _cmd_doctor(registry_root, runtime_root, host_root)

    elif args.command == "audit-purge":
        _cmd_audit_purge(
            runtime_root,
            args.trace_id,
            args.skill_id,
            args.older_than_days,
            args.all,
        )

    elif args.command == "scaffold":
        _cmd_scaffold(
            registry_root,
            runtime_root,
            host_root,
            local_skills_root,
            args.intent,
            args.channel,
            args.model,
            args.dry_run,
            args.out_dir,
        )

    elif args.command == "package-prepare":
        _cmd_package_prepare(
            registry_root,
            runtime_root,
            local_skills_root,
            args.skill_id,
            args.skill_file,
            args.target_channel,
            args.out_root,
            args.json,
        )

    elif args.command == "package-validate":
        _cmd_package_validate(
            registry_root,
            args.package_path,
            args.print_pr_command,
            args.json,
        )

    elif args.command == "package-pr":
        _cmd_package_pr(
            registry_root,
            args.registry_repo_root,
            args.package_path,
            args.remote,
            args.base,
            args.draft,
            args.dry_run,
            args.json,
        )

    elif args.command == "openapi":
        _cmd_openapi(args, runtime_root)

    elif args.command == "serve":
        _cmd_serve(args, registry_root, runtime_root, host_root)


def _cmd_serve(args, registry_root, runtime_root, host_root):
    """Start the HTTP API server."""
    import os
    from customer_facing.http_openapi_server import run_server, ServerConfig
    from customer_facing.neutral_api import NeutralRuntimeAPI

    host = args.host or os.environ.get("AGENT_SKILLS_HOST", "127.0.0.1")
    port = args.port or int(os.environ.get("AGENT_SKILLS_PORT", "8080"))
    api_key = args.api_key or os.environ.get("AGENT_SKILLS_API_KEY")
    cors = ""
    if args.cors_origins:
        cors = args.cors_origins
    elif os.environ.get("AGENT_SKILLS_CORS_ORIGINS"):
        cors = os.environ["AGENT_SKILLS_CORS_ORIGINS"]

    config = ServerConfig(
        host=host,
        port=port,
        api_key=api_key,
        cors_allowed_origins=cors,
    )

    gateway = SkillGateway(
        registry_root=registry_root,
        runtime_root=runtime_root,
        host_root=host_root,
    )
    api = NeutralRuntimeAPI(
        registry_root=registry_root,
        runtime_root=runtime_root,
        host_root=host_root,
    )

    run_server(api=api, gateway=gateway, config=config)


def _cmd_scaffold(
    registry_root: Path,
    runtime_root: Path,
    host_root: Path,
    local_skills_root: Path | None,
    intent: str,
    channel: str,
    model: str,
    dry_run: bool,
    out_dir: Path | None,
) -> None:
    import os

    from official_services.scaffold_service import generate_skill_from_prompt

    print(
        f"[scaffold] Generating skill for: {intent[:80]}{'...' if len(intent) > 80 else ''}"
    )
    has_key = bool(os.environ.get("OPENAI_API_KEY"))
    print(
        f"[scaffold] Mode: {'LLM (OpenAI)' if has_key else 'template (no OPENAI_API_KEY found)'}"
    )

    result = generate_skill_from_prompt(
        intent_description=intent,
        registry_root=str(registry_root),
        target_channel=channel,
        model=model,
        runtime_root=str(runtime_root),
        host_root=str(host_root),
    )

    skill_yaml: str = result["skill_yaml"]
    suggested_id: str = result["suggested_id"]
    capabilities_used: list = result["capabilities_used"]
    validation_errors: list = result["validation_errors"]
    planning_source: str | None = result.get("planning_source")
    planning_capability_id: str = result.get(
        "planning_capability_id", "agent.plan.generate"
    )
    scaffolder_mode: str = result.get("scaffolder_mode", "binding-first")

    print(f"[scaffold] Suggested id   : {suggested_id}")
    print(
        f"[scaffold] Capabilities   : {', '.join(capabilities_used) or '(none detected)'}"
    )
    print(f"[scaffold] Planner mode   : {scaffolder_mode}")
    print(
        "[scaffold] Planner source : "
        f"{planning_source or 'none'}"
        f" (capability: {planning_capability_id})"
    )

    if validation_errors:
        print("[scaffold] Validation warnings:")
        for err in validation_errors:
            print(f"           - {err}")
    else:
        print("[scaffold] Validation     : OK")

    if dry_run:
        print("\n" + "=" * 60)
        print(skill_yaml)
        print("=" * 60)
        return

    # Determine output path
    if out_dir:
        target_dir = out_dir
    else:
        resolved_local = local_skills_root or (runtime_root / "skills" / "local")
        # Parse domain and slug from suggested_id (domain.slug)
        parts = suggested_id.split(".", 1)
        domain = parts[0] if len(parts) >= 1 else "workflow"
        slug = parts[1].replace(".", "-") if len(parts) >= 2 else "custom"
        target_dir = resolved_local / domain / slug

    target_dir.mkdir(parents=True, exist_ok=True)
    target_file = target_dir / "skill.yaml"

    if target_file.exists():
        print(f"[scaffold] WARNING: {target_file} already exists — overwriting.")

    target_file.write_text(skill_yaml, encoding="utf-8")
    print(f"[scaffold] Written to     : {target_file}")
    print("[scaffold] Next steps:")
    print(f"           1. Review and edit {target_file}")
    print(f"           2. Run: skills run {suggested_id} --input '{{}}' to test")
    print("           3. Promote to experimental/ or community/ via PR when ready")


def _cmd_package_prepare(
    registry_root: Path,
    runtime_root: Path,
    local_skills_root: Path | None,
    skill_id: str | None,
    skill_file: Path | None,
    target_channel: str,
    out_root: Path | None,
    json_output: bool,
) -> None:
    resolved_local = local_skills_root or (runtime_root / "skills" / "local")
    if out_root is not None:
        package_out_root = out_root
    else:
        default_promotion_root = runtime_root / "artifacts" / "promotion_packages"
        legacy_officialization_root = (
            runtime_root / "artifacts" / "officialization_packages"
        )
        package_out_root = (
            legacy_officialization_root
            if legacy_officialization_root.exists()
            and not default_promotion_root.exists()
            else default_promotion_root
        )
    package_out_root.mkdir(parents=True, exist_ok=True)

    result = prepare_promotion_package(
        local_skills_root=resolved_local,
        registry_root=registry_root,
        target_channel=target_channel,
        out_root=package_out_root,
        skill_id=skill_id,
        skill_file=skill_file,
    )

    if json_output:
        print(
            json.dumps(
                {
                    "ok": True,
                    "command": "package-prepare",
                    "skill_id": result.skill_id,
                    "target_channel": result.target_channel,
                    "package_root": str(result.package_root),
                    "payload_skill_path": str(result.payload_skill_path),
                    "next": {
                        "validate_command": (
                            f'python skills.py package-validate "{result.package_root}" --print-pr-command --json'
                        )
                    },
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return

    print("[package-prepare] Package created")
    print(f"[package-prepare] Skill ID       : {result.skill_id}")
    print(f"[package-prepare] Target channel: {result.target_channel}")
    print(f"[package-prepare] Package root   : {result.package_root}")
    print(f"[package-prepare] Payload skill  : {result.payload_skill_path}")
    print("[package-prepare] Next step:")
    print(
        f'  python skills.py package-validate "{result.package_root}" --print-pr-command'
    )


def _cmd_package_validate(
    registry_root: Path,
    package_path: Path,
    print_pr_command: bool,
    json_output: bool,
) -> None:
    result = validate_promotion_package(
        package_root=package_path,
        registry_root=registry_root,
    )

    payload = {
        "ok": len(result.errors) == 0,
        "command": "package-validate",
        "skill_id": result.skill_id,
        "target_channel": result.target_channel,
        "warnings": result.warnings,
        "errors": result.errors,
    }

    if json_output:
        if print_pr_command and not result.errors:
            payload["suggested_pr_flow"] = _build_pr_flow_payload(
                registry_root, package_path
            )
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        if result.errors:
            raise SystemExit(2)
        return

    print(f"[package-validate] Skill ID       : {result.skill_id or '(unknown)'}")
    print(f"[package-validate] Target channel: {result.target_channel or '(unknown)'}")

    if result.warnings:
        print("[package-validate] Warnings:")
        for warning in result.warnings:
            print(f"  - {warning}")

    if result.errors:
        print("[package-validate] Errors:")
        for error in result.errors:
            print(f"  - {error}")
        raise SystemExit(2)

    print("[package-validate] Validation: OK")

    if print_pr_command:
        _print_pr_commands(registry_root, package_path)


def _build_pr_flow_payload(
    registry_root: Path, package_path: Path
) -> dict[str, object] | None:
    manifest_path = package_path / "package_manifest.json"
    if not manifest_path.exists():
        return None

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    skill_id = manifest.get("skill_id", "unknown.skill")
    target_channel = manifest.get("target_channel", "experimental")

    if isinstance(skill_id, str) and "." in skill_id:
        domain, slug = skill_id.split(".", 1)
    else:
        domain, slug = "unknown", "skill"

    payload_skill = (
        package_path
        / "payload"
        / "skills"
        / target_channel
        / domain
        / slug
        / "skill.yaml"
    )
    evidence_answers = package_path / "evidence" / "admission_answers.yaml"
    pr_template = package_path / "pr_body_template.md"
    branch_name = f"promote/{target_channel}/{skill_id}".replace(".", "-")
    target_rel = f"skills/{target_channel}/{domain}/{slug}/skill.yaml"

    return {
        "branch": branch_name,
        "target_rel": target_rel,
        "payload_skill": str(payload_skill),
        "pr_template": str(pr_template),
        "evidence_answers": str(evidence_answers),
        "commands": [
            f'Set-Location "{registry_root}"',
            f'git checkout -b "{branch_name}"',
            f'New-Item -ItemType Directory -Force -Path "skills/{target_channel}/{domain}/{slug}" | Out-Null',
            f'Copy-Item "{payload_skill}" "{target_rel}"',
            "python tools/validate_registry.py",
            "python tools/generate_catalog.py",
            "python tools/governance_guardrails.py",
            "python tools/capability_governance_guardrails.py",
            "python tools/enforce_capability_sunset.py",
            f'git add "{target_rel}" catalog/*.json',
            f'git commit -m "Promote {skill_id} to {target_channel}"',
            "git push -u origin HEAD",
            (
                'gh pr create --title "Promote '
                f'{skill_id} to {target_channel}" --body-file "{pr_template}"'
            ),
        ],
    }


def _print_pr_commands(registry_root: Path, package_path: Path) -> None:
    flow = _build_pr_flow_payload(registry_root, package_path)
    if flow is None:
        return

    flow.get("branch")
    flow.get("target_rel")
    flow.get("payload_skill")
    flow.get("pr_template")
    evidence_answers = flow.get("evidence_answers")
    commands = flow.get("commands", [])

    print("[package-validate] Suggested PR flow (manual review + explicit commands):")
    for idx, cmd in enumerate(commands, start=1):
        print(f" {idx:>2}. {cmd}")
    print(f"     # Fill checklist answers from: {evidence_answers}")


def _cmd_package_pr(
    registry_root: Path,
    registry_repo_root: Path | None,
    package_path: Path,
    remote: str,
    base: str,
    draft: bool,
    dry_run: bool,
    json_output: bool,
) -> None:
    result_payload: dict[str, object] = {
        "ok": False,
        "command": "package-pr",
        "dry_run": dry_run,
        "steps": [],
    }
    branch_created = False
    original_branch: str | None = None
    gh_available = True

    def _record_step(name: str, ok: bool, detail: str | None = None) -> None:
        step = {"name": name, "ok": ok}
        if detail:
            step["detail"] = detail
        result_payload["steps"].append(step)

    def _finish_with_error(message: str, exit_code: int = 2) -> None:
        cleanup_notes: list[str] = []

        if branch_created:
            if original_branch:
                cp_checkout = _run(["git", "checkout", original_branch])
                if cp_checkout.returncode == 0:
                    cleanup_notes.append(
                        f"checked out original branch '{original_branch}'"
                    )
                else:
                    cleanup_notes.append(
                        "failed to return to original branch before cleanup"
                    )

            cp_delete = _run(["git", "branch", "-D", branch_name])
            if cp_delete.returncode == 0:
                cleanup_notes.append(f"deleted temporary branch '{branch_name}'")
            else:
                cleanup_notes.append(
                    f"failed to delete temporary branch '{branch_name}'"
                )

        result_payload["ok"] = False
        result_payload["error"] = message
        _record_step("error", False, message)
        if cleanup_notes:
            result_payload["cleanup"] = cleanup_notes
        if json_output:
            print(json.dumps(result_payload, indent=2, ensure_ascii=False))
            raise SystemExit(exit_code)
        raise SystemExit(message)

    def _finish_success() -> None:
        result_payload["ok"] = True
        if json_output:
            print(json.dumps(result_payload, indent=2, ensure_ascii=False))

    # Always validate package before any git/gh side effects.
    validation = validate_promotion_package(
        package_root=package_path,
        registry_root=registry_root,
    )
    result_payload["validation"] = {
        "errors": validation.errors,
        "warnings": validation.warnings,
        "skill_id": validation.skill_id,
        "target_channel": validation.target_channel,
    }
    if validation.errors:
        if not json_output:
            print("[package-pr] Validation errors:")
            for err in validation.errors:
                print(f"  - {err}")
        _finish_with_error("package validation failed", exit_code=2)
    _record_step("validate_package", True)

    if not validation.skill_id or not validation.target_channel:
        _finish_with_error("missing skill_id or target_channel in package manifest")

    skill_id = validation.skill_id
    target_channel = validation.target_channel
    if "." not in skill_id:
        _finish_with_error(f"invalid skill id in package: {skill_id}")
    domain, slug = skill_id.split(".", 1)

    repo_root = registry_repo_root or registry_root
    if not repo_root.exists():
        _finish_with_error(f"registry repo root does not exist: {repo_root}")

    payload_skill = (
        package_path
        / "payload"
        / "skills"
        / target_channel
        / domain
        / slug
        / "skill.yaml"
    )
    if not payload_skill.exists():
        _finish_with_error(f"missing payload skill: {payload_skill}")

    pr_template = package_path / "pr_body_template.md"
    if not pr_template.exists():
        _finish_with_error(f"missing PR template file: {pr_template}")

    target_rel = Path("skills") / target_channel / domain / slug / "skill.yaml"
    target_abs = repo_root / target_rel
    branch_name = f"promote/{target_channel}/{skill_id}".replace(".", "-")

    result_payload["plan"] = {
        "repo_root": str(repo_root),
        "branch": branch_name,
        "skill_id": skill_id,
        "target_channel": target_channel,
        "target_file": str(target_abs),
        "remote": remote,
        "base": base,
        "draft": draft,
        "package_path": str(package_path),
    }

    def _run(cmd: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            cmd, cwd=repo_root, check=False, text=True, capture_output=True
        )

    def _require_ok(cp: subprocess.CompletedProcess, label: str) -> None:
        if cp.returncode != 0:
            detail = (cp.stderr or cp.stdout or "").strip()
            _finish_with_error(f"{label} failed: {detail}")
        _record_step(label, True)

    if not json_output:
        print("[package-pr] Plan")
        print(f"  Repo root    : {repo_root}")
        print(f"  Branch       : {branch_name}")
        print(f"  Skill        : {skill_id}")
        print(f"  Target file  : {target_abs}")
        print(f"  Remote/base  : {remote} / {base}")

    if dry_run:
        _record_step("dry_run", True, "No git/gh commands executed")
        result_payload["ok"] = True
        if json_output:
            print(json.dumps(result_payload, indent=2, ensure_ascii=False))
        else:
            print("[package-pr] Dry-run enabled. No git/gh commands executed.")
        return

    # Pre-flight checks.
    try:
        git_check = _run(["git", "rev-parse", "--is-inside-work-tree"])
    except FileNotFoundError as exc:
        raise SystemExit("[package-pr] git executable not found in PATH.") from exc
    _require_ok(git_check, "git repository check")

    try:
        gh_check = _run(["gh", "--version"])
        gh_available = gh_check.returncode == 0
    except FileNotFoundError:
        gh_available = False

    if gh_available:
        _record_step("gh availability check", True)
    else:
        _record_step(
            "gh availability check",
            False,
            "gh executable not found; package-pr will output a manual gh pr create command",
        )

    status = _run(["git", "status", "--porcelain"])
    _require_ok(status, "git status")
    if status.stdout.strip():
        _finish_with_error(
            "registry repo has uncommitted changes; commit/stash them first"
        )

    cp = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    _require_ok(cp, "resolve current branch")
    original_branch = (cp.stdout or "").strip() or None

    cp = _run(["git", "rev-parse", "--verify", base])
    _require_ok(cp, f"resolve base branch '{base}'")

    cp = _run(["git", "checkout", base])
    _require_ok(cp, f"checkout base branch '{base}'")

    cp = _run(["git", "pull", "--ff-only", remote, base])
    _require_ok(cp, f"fast-forward base branch '{base}' from {remote}")

    cp = _run(["git", "rev-parse", "--verify", branch_name])
    if cp.returncode == 0:
        _finish_with_error(f"target branch '{branch_name}' already exists locally")

    # Create branch explicitly from base.
    cp = _run(["git", "checkout", "-b", branch_name, base])
    _require_ok(cp, "branch creation")
    branch_created = True

    target_abs.parent.mkdir(parents=True, exist_ok=True)
    target_abs.write_text(payload_skill.read_text(encoding="utf-8"), encoding="utf-8")
    _record_step("apply_payload", True, str(target_abs))

    # Run required governance checks before PR creation.
    for cmd, label in [
        ([sys.executable, "tools/validate_registry.py"], "validate_registry"),
        ([sys.executable, "tools/generate_catalog.py"], "generate_catalog"),
        ([sys.executable, "tools/governance_guardrails.py"], "governance_guardrails"),
        (
            [sys.executable, "tools/capability_governance_guardrails.py"],
            "capability_governance_guardrails",
        ),
        (
            [sys.executable, "tools/enforce_capability_sunset.py"],
            "enforce_capability_sunset",
        ),
    ]:
        cp = _run(cmd)
        _require_ok(cp, label)

    cp = _run(["git", "add", str(target_rel), "catalog/*.json"])
    _require_ok(cp, "git add")

    cp = _run(["git", "commit", "-m", f"Promote {skill_id} to {target_channel}"])
    _require_ok(cp, "git commit")

    cp = _run(["git", "push", "-u", remote, "HEAD"])
    _require_ok(cp, "git push")

    pr_cmd = [
        "gh",
        "pr",
        "create",
        "--base",
        base,
        "--title",
        f"Promote {skill_id} to {target_channel}",
        "--body-file",
        str(pr_template),
    ]
    if draft:
        pr_cmd.append("--draft")

    if gh_available:
        cp = _run(pr_cmd)
        _require_ok(cp, "gh pr create")

        pr_output = (cp.stdout or "").strip()
        result_payload["pr"] = {
            "created": True,
            "title": f"Promote {skill_id} to {target_channel}",
            "base": base,
            "remote": remote,
            "draft": draft,
            "output": pr_output,
        }

        if not json_output:
            print("[package-pr] PR created successfully.")
            if pr_output:
                print(pr_output)
    else:
        manual_cmd = " ".join(
            [
                "gh",
                "pr",
                "create",
                "--base",
                base,
                "--title",
                f'"Promote {skill_id} to {target_channel}"',
                "--body-file",
                f'"{pr_template}"',
                "--draft" if draft else "",
            ]
        ).strip()

        result_payload["pr"] = {
            "created": False,
            "reason": "gh not available",
            "manual_command": manual_cmd,
        }
        if not json_output:
            print("[package-pr] Branch pushed, but gh is not available in PATH.")
            print("[package-pr] Create the PR manually with:")
            print(f"  {manual_cmd}")

    _finish_success()


def _cmd_openapi(args, runtime_root: Path) -> None:
    tooling_root = runtime_root / "tooling"

    if args.openapi_command == "verify-bindings":
        cmd = [
            sys.executable,
            str(tooling_root / "verify_openapi_bindings.py"),
        ]
        if args.scenario is not None:
            cmd.extend(["--scenario", str(args.scenario)])
        if args.all:
            cmd.append("--all")
        if args.scenarios_dir is not None:
            cmd.extend(["--scenarios-dir", str(args.scenarios_dir)])
        if args.report_file is not None:
            cmd.extend(["--report-file", str(args.report_file)])

        completed = subprocess.run(cmd, check=False)
        if completed.returncode != 0:
            raise SystemExit(completed.returncode)
        return

    if args.openapi_command == "verify-invoker":
        cmd = [
            sys.executable,
            str(tooling_root / "verify_openapi_invoker_runtime.py"),
        ]
        completed = subprocess.run(cmd, check=False)
        if completed.returncode != 0:
            raise SystemExit(completed.returncode)
        return

    if args.openapi_command == "verify-errors":
        cmd = [
            sys.executable,
            str(tooling_root / "verify_openapi_error_contract.py"),
        ]
        completed = subprocess.run(cmd, check=False)
        if completed.returncode != 0:
            raise SystemExit(completed.returncode)
        return

    raise ValueError(f"Unsupported openapi command '{args.openapi_command}'.")


def _cmd_run(
    registry_root: Path,
    runtime_root: Path,
    host_root: Path,
    skill_id: str,
    input_json: str | None,
    input_file: str | None,
    trace_id: str | None,
    required_conformance_profile: str | None,
    audit_mode: str | None,
    local_skills_root: Path | None = None,
) -> None:

    if input_json and input_file:
        raise ValueError("Use either --input or --input-file")

    if input_file:
        with open(input_file, "r", encoding="utf-8") as f:
            inputs = json.load(f)

    elif input_json:
        inputs = json.loads(input_json)

    else:
        inputs = {}

    engine = _build_engine(registry_root, runtime_root, host_root, local_skills_root)

    request = ExecutionRequest(
        skill_id=skill_id,
        inputs=inputs,
        options=ExecutionOptions(
            required_conformance_profile=required_conformance_profile,
            audit_mode=audit_mode,
        ),
        trace_id=trace_id,
        channel="cli",
    )

    result = engine.execute(request)

    print(json.dumps(result.outputs, indent=2, ensure_ascii=False))


def _cmd_describe(registry_root: Path, skill_id: str) -> None:

    skill_loader = YamlSkillLoader(registry_root)

    skill = skill_loader.get_skill(skill_id)

    print(
        json.dumps(
            {
                "id": skill.id,
                "name": skill.name,
                "description": skill.description,
                "inputs": list(skill.inputs.keys()),
                "outputs": list(skill.outputs.keys()),
                "steps": [s.id for s in skill.steps],
            },
            indent=2,
            ensure_ascii=False,
        )
    )


def _cmd_discover(
    registry_root: Path,
    runtime_root: Path,
    host_root: Path,
    intent: str,
    domain: str | None,
    role: str | None,
    limit: int,
    json_output: bool,
    local_skills_root: Path | None = None,
) -> None:
    gateway = SkillGateway(
        registry_root=registry_root,
        runtime_root=runtime_root,
        host_root=host_root,
        local_skills_root=local_skills_root,
    )
    results = gateway.discover(
        intent=intent,
        domain=domain,
        role_filter=role,
        limit=limit,
    )

    payload = {
        "intent": intent,
        "domain": domain,
        "role_filter": role,
        "limit": limit,
        "results": [r.to_dict() for r in results],
    }

    if json_output:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return

    print(json.dumps(payload, indent=2, ensure_ascii=False))


def _cmd_list_skills(
    registry_root: Path,
    runtime_root: Path,
    host_root: Path,
    domain: str | None,
    role: str | None,
    status: str | None,
    invocation: str | None,
    json_output: bool,
    local_skills_root: Path | None = None,
) -> None:
    gateway = SkillGateway(
        registry_root=registry_root,
        runtime_root=runtime_root,
        host_root=host_root,
        local_skills_root=local_skills_root,
    )
    results = gateway.list_skills(
        domain=domain,
        role=role,
        status=status,
        invocation=invocation,
    )

    payload = {
        "filters": {
            "domain": domain,
            "role": role,
            "status": status,
            "invocation": invocation,
        },
        "count": len(results),
        "skills": [s.to_dict() for s in results],
    }

    if json_output:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return

    print(json.dumps(payload, indent=2, ensure_ascii=False))


def _cmd_attach(
    registry_root: Path,
    runtime_root: Path,
    host_root: Path,
    skill_id: str,
    target_type: str,
    target_ref: str,
    input_json: str | None,
    input_file: str | None,
    trace_id: str | None,
    include_trace: bool,
    required_conformance_profile: str | None,
    audit_mode: str | None,
    json_output: bool,
    local_skills_root: Path | None = None,
) -> None:
    if input_json and input_file:
        raise ValueError("Use either --input or --input-file")

    if input_file:
        # Accept UTF-8 files with or without BOM for smoother PowerShell interop.
        with open(input_file, "r", encoding="utf-8-sig") as f:
            inputs = json.load(f)
    elif input_json:
        inputs = json.loads(input_json)
    else:
        inputs = {}

    if not isinstance(inputs, dict):
        raise ValueError("attach inputs must be a JSON object")

    gateway = SkillGateway(
        registry_root=registry_root,
        runtime_root=runtime_root,
        host_root=host_root,
        local_skills_root=local_skills_root,
    )

    try:
        result = gateway.attach(
            skill_id=skill_id,
            target_type=target_type,
            target_ref=target_ref,
            inputs=inputs,
            trace_id=trace_id,
            include_trace=include_trace,
            required_conformance_profile=required_conformance_profile,
            audit_mode=audit_mode,
        )
    except Exception as e:
        if json_output:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "error": {
                            "type": type(e).__name__,
                            "message": str(e),
                        },
                    },
                    indent=2,
                    ensure_ascii=False,
                )
            )
            raise SystemExit(2)
        raise

    payload = result.to_dict()
    if json_output:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return

    print(json.dumps(payload, indent=2, ensure_ascii=False))


def _cmd_gateway_diagnostics(
    registry_root: Path,
    runtime_root: Path,
    host_root: Path,
    json_output: bool,
    local_skills_root: Path | None = None,
) -> None:
    gateway = SkillGateway(
        registry_root=registry_root,
        runtime_root=runtime_root,
        host_root=host_root,
        local_skills_root=local_skills_root,
    )
    payload = gateway.diagnostics()

    if json_output:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return

    print(json.dumps(payload, indent=2, ensure_ascii=False))


def _cmd_gateway_reset_metrics(
    registry_root: Path,
    runtime_root: Path,
    host_root: Path,
    clear_cache: bool,
    json_output: bool,
    local_skills_root: Path | None = None,
) -> None:
    gateway = SkillGateway(
        registry_root=registry_root,
        runtime_root=runtime_root,
        host_root=host_root,
        local_skills_root=local_skills_root,
    )
    payload = gateway.reset_diagnostics_metrics(clear_cache=clear_cache)

    if json_output:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return

    print(json.dumps(payload, indent=2, ensure_ascii=False))


def _cmd_trace(
    registry_root: Path,
    runtime_root: Path,
    host_root: Path,
    skill_id: str,
    input_json: str | None,
    input_file: str | None,
    trace_id: str | None,
    required_conformance_profile: str | None,
    audit_mode: str | None,
    local_skills_root: Path | None = None,
) -> None:
    if input_json and input_file:
        raise ValueError("Use either --input or --input-file")

    if input_file:
        with open(input_file, "r", encoding="utf-8") as f:
            inputs = json.load(f)

    elif input_json:
        inputs = json.loads(input_json)

    else:
        inputs = {}

    engine = _build_engine(registry_root, runtime_root, host_root, local_skills_root)

    request = ExecutionRequest(
        skill_id=skill_id,
        inputs=inputs,
        options=ExecutionOptions(
            required_conformance_profile=required_conformance_profile,
            audit_mode=audit_mode,
        ),
        trace_id=trace_id,
        channel="cli",
    )

    # Enable tracing
    def trace_event(event):
        print(f"[{event.type}] {event.message}")
        if event.step_id:
            print(f"  step: {event.step_id}")
        # print binding/service info or produced output if available
        if event.data:
            # ensure consistent ordering
            for k, v in event.data.items():
                print(f"  {k}: {v}")
        print()

    result = engine.execute(request, trace_callback=trace_event)

    print(json.dumps(result.outputs, indent=2, ensure_ascii=False))


def _cmd_activate(runtime_root: Path, host_root: Path, capability: str | None) -> None:

    binding_registry = BindingRegistry(runtime_root, host_root)

    service_loader = ServiceDescriptorLoader(host_root)
    override_loader = OverrideIntentLoader(host_root)
    state_store = BindingStateStore(host_root)

    quality_gate = QualityGate()

    activation = BindingActivationService(
        runtime_root=runtime_root,
        host_root=host_root,
        binding_registry=binding_registry,
        service_loader=service_loader,
        override_loader=override_loader,
        state_store=state_store,
        quality_gate=quality_gate,
    )

    if capability:
        binding_id = activation.activate_capability(capability)

        print(f"{capability} -> {binding_id}")

    else:
        active = activation.activate_all()

        print(json.dumps(active, indent=2, ensure_ascii=False))


def _cmd_doctor(registry_root: Path, runtime_root: Path, host_root: Path) -> None:

    errors = 0
    warnings = 0

    def ok(msg):
        print(f"[OK] {msg}")

    def warn(msg):
        nonlocal warnings
        warnings += 1
        print(f"[WARN] {msg}")

    def error(msg):
        nonlocal errors
        errors += 1
        print(f"[ERROR] {msg}")

    # Workspace checks
    if registry_root.exists():
        ok(f"registry root found: {registry_root}")
    else:
        error(f"registry root not found: {registry_root}")

    if runtime_root.exists():
        ok(f"runtime root found: {runtime_root}")
    else:
        error(f"runtime root not found: {runtime_root}")

    if host_root.exists():
        ok(f"host root found: {host_root}")
    else:
        error(f"host root not found: {host_root}")

    if errors > 0:
        print(f"\nDoctor completed\n\nErrors: {errors}\nWarnings: {warnings}")
        return

    # Registry checks
    skill_loader = YamlSkillLoader(registry_root)
    capability_loader = YamlCapabilityLoader(registry_root)
    skills = {}
    capabilities = {}
    try:
        # Load all skills by scanning files
        skills_root = registry_root / "skills"
        if skills_root.exists():
            for skill_file in skills_root.glob("**/*skill.yaml"):
                try:
                    raw = yaml.safe_load(skill_file.read_text(encoding="utf-8"))
                    skill_id = raw.get("id")
                    if skill_id:
                        skills[skill_id] = skill_loader._normalize_skill(
                            raw, skill_file
                        )
                except Exception:
                    pass  # Skip invalid
        ok(f"skills loaded: {len(skills)}")
    except Exception as e:
        error(f"failed to load skills: {e}")

    try:
        capabilities = capability_loader.get_all_capabilities()
        ok(f"capabilities loaded: {len(capabilities)}")
    except Exception as e:
        error(f"failed to load capabilities: {e}")

    # If failed, try to scan
    if not capabilities:
        try:
            capabilities_root = registry_root / "capabilities"
            if capabilities_root.exists():
                for cap_file in capabilities_root.glob("*.yaml"):
                    try:
                        raw = yaml.safe_load(cap_file.read_text(encoding="utf-8"))
                        cap_id = raw.get("id")
                        if cap_id:
                            capabilities[cap_id] = (
                                capability_loader._normalize_capability(raw, cap_file)
                            )
                    except Exception:
                        pass
            ok(f"capabilities loaded: {len(capabilities)}")
        except Exception as e:
            error(f"failed to load capabilities: {e}")

    # Runtime checks
    binding_registry = None
    try:
        binding_registry = BindingRegistry(runtime_root, host_root)
        ok("binding registry initialized")
    except Exception as e:
        error(f"failed to initialize binding registry: {e}")

    # Binding integrity
    if binding_registry and capabilities:
        for cap_id in capabilities:
            bindings = binding_registry.get_bindings_for_capability(cap_id)
            if not bindings:
                warn(f"capability '{cap_id}' has no binding")

    # Skill executability
    if skill_loader and binding_registry and capabilities:
        for skill in skills.values():
            missing = []
            for step in skill.steps:
                if step.uses.startswith("skill:"):
                    continue
                cap_id = step.uses
                if cap_id not in capabilities:
                    missing.append(cap_id)
                    continue
                if not binding_registry.get_bindings_for_capability(cap_id):
                    missing.append(cap_id)
            if missing:
                warn(
                    f"skill '{skill.id}' not executable (missing bindings for: {', '.join(missing)})"
                )

    # Python service checks
    if binding_registry:
        import importlib

        for service_id, service in binding_registry._services_by_id.items():
            if service.kind == "pythoncall":
                try:
                    importlib.import_module(service.module)
                    ok(f"module {service.module} importable")
                except ImportError as e:
                    error(f"module {service.module} not importable: {e}")

    # Host configuration checks
    host_config_dir = host_root / ".agent-skills"
    if host_config_dir.exists():
        ok("host configuration directory exists")
        for file in ["active_bindings.json", "services.yaml", "overrides.yaml"]:
            if (host_config_dir / file).exists():
                ok(f"host config file {file} exists")
            else:
                warn(f"host config file {file} missing")
    else:
        warn("host configuration directory missing")

    print(f"\nDoctor completed\n\nErrors: {errors}\nWarnings: {warnings}")


def _build_engine(
    registry_root: Path,
    runtime_root: Path,
    host_root: Path,
    local_skills_root: Path | None = None,
) -> ExecutionEngine:
    components = build_runtime_components(
        registry_root=registry_root,
        runtime_root=runtime_root,
        host_root=host_root,
        mcp_client_registry=None,
        local_skills_root=local_skills_root,
    )
    return components.engine


def _cmd_explain_capability(
    registry_root: Path,
    runtime_root: Path,
    host_root: Path,
    capability_id: str,
    required_conformance_profile: str | None,
) -> None:
    from customer_facing.neutral_api import NeutralRuntimeAPI

    api = NeutralRuntimeAPI(
        registry_root=registry_root,
        runtime_root=runtime_root,
        host_root=host_root,
    )
    explanation = api.explain_capability_resolution(
        capability_id,
        required_conformance_profile=required_conformance_profile,
    )
    print(json.dumps(explanation, indent=2, ensure_ascii=False))


def _cmd_skill_governance(
    registry_root: Path,
    runtime_root: Path,
    host_root: Path,
    min_state: str | None,
    limit: int,
) -> None:
    from customer_facing.neutral_api import NeutralRuntimeAPI

    api = NeutralRuntimeAPI(
        registry_root=registry_root,
        runtime_root=runtime_root,
        host_root=host_root,
    )
    result = api.list_skill_governance(min_state=min_state, limit=limit)
    print(json.dumps(result, indent=2, ensure_ascii=False))


def _cmd_audit_purge(
    runtime_root: Path,
    trace_id: str | None,
    skill_id: str | None,
    older_than_days: int | None,
    purge_all: bool,
) -> None:
    recorder = AuditRecorder(runtime_root)
    result = recorder.purge(
        trace_id=trace_id,
        skill_id=skill_id,
        older_than_days=older_than_days,
        purge_all=purge_all,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

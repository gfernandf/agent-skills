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

from runtime.active_binding_map import ActiveBindingMap
from runtime.binding_executor import BindingExecutor
from runtime.binding_registry import BindingRegistry
from runtime.audit import AuditRecorder
from runtime.binding_resolver import BindingResolver
from runtime.capability_executor import DefaultCapabilityExecutor
from runtime.capability_loader import YamlCapabilityLoader
from runtime.execution_engine import ExecutionEngine
from runtime.execution_planner import ExecutionPlanner
from runtime.nested_skill_runner import NestedSkillRunner
from runtime.protocol_router import ProtocolRouter
from runtime.reference_resolver import ReferenceResolver
from runtime.request_builder import RequestBuilder
from runtime.response_mapper import ResponseMapper
from runtime.service_resolver import ServiceResolver
from runtime.skill_loader import YamlSkillLoader

from runtime.openapi_invoker import OpenAPIInvoker
from runtime.openrpc_invoker import OpenRPCInvoker
from runtime.mcp_invoker import MCPInvoker
from runtime.pythoncall_invoker import PythonCallInvoker
from runtime.engine_factory import build_runtime_components
from runtime.models import ExecutionOptions, ExecutionRequest


def main() -> None:

    parser = argparse.ArgumentParser(prog="skills")
    sub = parser.add_subparsers(dest="command", required=True)

    # Common arguments for roots
    def add_root_args(cmd_parser):
        cmd_parser.add_argument("--registry-root", type=Path, default=None, help="Path to the registry root directory")
        cmd_parser.add_argument("--runtime-root", type=Path, default=None, help="Path to the runtime root directory")
        cmd_parser.add_argument("--host-root", type=Path, default=None, help="Path to the host root directory")
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
    run_cmd.add_argument("--trace-id", default=None, help="Optional trace id for correlation")
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

    activate_cmd = sub.add_parser("activate", help="Apply override activation")
    activate_cmd.add_argument("--capability", default=None)
    add_root_args(activate_cmd)

    trace_cmd = sub.add_parser("trace", help="Execute a skill with detailed tracing")
    trace_cmd.add_argument("skill_id")
    trace_cmd.add_argument("--input", default=None)
    trace_cmd.add_argument("--input-file", default=None)
    trace_cmd.add_argument("--trace-id", default=None, help="Optional trace id for correlation")
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

    audit_purge_cmd = sub.add_parser("audit-purge", help="Purge persisted skill execution audit records")
    audit_purge_cmd.add_argument("--trace-id", default=None)
    audit_purge_cmd.add_argument("--skill-id", default=None)
    audit_purge_cmd.add_argument("--older-than-days", type=int, default=None)
    audit_purge_cmd.add_argument("--all", action="store_true", help="Delete all persisted audit records")
    add_root_args(audit_purge_cmd)

    explain_cap_cmd = sub.add_parser("explain-capability", help="Explain effective binding resolution and conformance chain")
    explain_cap_cmd.add_argument("capability_id")
    explain_cap_cmd.add_argument(
        "--required-conformance-profile",
        choices=["strict", "standard", "experimental"],
        default=None,
        help="Optional minimum conformance profile used for eligibility planning.",
    )
    add_root_args(explain_cap_cmd)

    gov_cmd = sub.add_parser("skill-governance", help="List skill governance entries from operational quality catalog")
    gov_cmd.add_argument("--min-state", default=None, choices=["draft", "validated", "lab-verified", "trusted", "recommended"])
    gov_cmd.add_argument("--limit", type=int, default=20)
    add_root_args(gov_cmd)

    doctor_cmd = sub.add_parser("doctor", help="Run system health checks")
    add_root_args(doctor_cmd)

    openapi_cmd = sub.add_parser("openapi", help="Run OpenAPI verification and diagnostics")
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

    elif args.command == "openapi":

        _cmd_openapi(args, runtime_root)


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
                        skills[skill_id] = skill_loader._normalize_skill(raw, skill_file)
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
                            capabilities[cap_id] = capability_loader._normalize_capability(raw, cap_file)
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
                warn(f"skill '{skill.id}' not executable (missing bindings for: {', '.join(missing)})")

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
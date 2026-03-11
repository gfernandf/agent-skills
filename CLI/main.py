from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

from customization.binding_activation import BindingActivationService
from customization.binding_state_store import BindingStateStore
from customization.override_intent_loader import OverrideIntentLoader
from customization.quality_gate import QualityGate
from customization.service_descriptor_loader import ServiceDescriptorLoader

from runtime.active_binding_map import ActiveBindingMap
from runtime.binding_executor import BindingExecutor
from runtime.binding_registry import BindingRegistry
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


def main() -> None:

    parser = argparse.ArgumentParser(prog="skills")
    sub = parser.add_subparsers(dest="command", required=True)

    # Common arguments for roots
    def add_root_args(cmd_parser):
        cmd_parser.add_argument("--registry-root", type=Path, default=None, help="Path to the registry root directory")
        cmd_parser.add_argument("--runtime-root", type=Path, default=None, help="Path to the runtime root directory")
        cmd_parser.add_argument("--host-root", type=Path, default=None, help="Path to the host root directory")

    run_cmd = sub.add_parser("run", help="Execute a skill")
    run_cmd.add_argument("skill_id")
    run_cmd.add_argument("--input", default=None)
    run_cmd.add_argument("--input-file", default=None)
    run_cmd.add_argument("--trace-id", default=None, help="Optional trace id for correlation")
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
    add_root_args(trace_cmd)

    doctor_cmd = sub.add_parser("doctor", help="Run system health checks")
    add_root_args(doctor_cmd)

    args = parser.parse_args()

    # Resolve roots with defaults
    runtime_root = args.runtime_root or Path.cwd()
    registry_root = args.registry_root or (runtime_root.parent / "agent-skill-registry")
    host_root = args.host_root or runtime_root

    if args.command == "run":

        _cmd_run(
            registry_root,
            runtime_root,
            host_root,
            args.skill_id,
            args.input,
            args.input_file,
            args.trace_id,
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
        )

    elif args.command == "doctor":

        _cmd_doctor(registry_root, runtime_root, host_root)


def _cmd_run(
    registry_root: Path,
    runtime_root: Path,
    host_root: Path,
    skill_id: str,
    input_json: str | None,
    input_file: str | None,
    trace_id: str | None,
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

    engine = _build_engine(registry_root, runtime_root, host_root)

    from runtime.models import ExecutionRequest

    request = ExecutionRequest(
        skill_id=skill_id,
        inputs=inputs,
        trace_id=trace_id,
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
) -> None:
    print("DEBUG: _cmd_trace called")

    if input_json and input_file:
        raise ValueError("Use either --input or --input-file")

    if input_file:

        with open(input_file, "r", encoding="utf-8") as f:
            inputs = json.load(f)

    elif input_json:

        inputs = json.loads(input_json)

    else:

        inputs = {}

    engine = _build_engine(registry_root, runtime_root, host_root)

    from runtime.models import ExecutionRequest

    request = ExecutionRequest(
        skill_id=skill_id,
        inputs=inputs,
        trace_id=trace_id,
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
) -> ExecutionEngine:

    skill_loader = YamlSkillLoader(registry_root)

    capability_loader = YamlCapabilityLoader(registry_root)

    planner = ExecutionPlanner()

    resolver = ReferenceResolver()

    binding_registry = BindingRegistry(runtime_root, host_root)

    active_map = ActiveBindingMap(host_root)

    binding_resolver = BindingResolver(binding_registry, active_map)

    service_resolver = ServiceResolver(binding_registry)

    request_builder = RequestBuilder()

    response_mapper = ResponseMapper()

    openapi_invoker = OpenAPIInvoker()

    openrpc_invoker = OpenRPCInvoker()

    mcp_invoker = MCPInvoker(client_registry=None)

    pythoncall_invoker = PythonCallInvoker()

    protocol_router = ProtocolRouter(
        openapi_invoker=openapi_invoker,
        mcp_invoker=mcp_invoker,
        openrpc_invoker=openrpc_invoker,
        pythoncall_invoker=pythoncall_invoker,
    )

    binding_executor = BindingExecutor(
        binding_registry=binding_registry,
        binding_resolver=binding_resolver,
        service_resolver=service_resolver,
        request_builder=request_builder,
        protocol_router=protocol_router,
        response_mapper=response_mapper,
    )

    capability_executor = DefaultCapabilityExecutor(binding_executor)

    engine = ExecutionEngine(
        skill_loader=skill_loader,
        capability_loader=capability_loader,
        execution_planner=planner,
        reference_resolver=resolver,
        capability_executor=capability_executor,
        nested_skill_runner=NestedSkillRunner(None),
    )

    engine.nested_skill_runner.execution_engine = engine

    return engine
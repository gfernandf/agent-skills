from __future__ import annotations

import argparse
import json
from pathlib import Path

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
from runtime.input_mapper import build_step_input  # indirectly used by engine
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

    run_cmd = sub.add_parser("run", help="Execute a skill")
    run_cmd.add_argument("skill_id")
    run_cmd.add_argument("--input", default="{}")

    describe_cmd = sub.add_parser("describe", help="Describe a skill")
    describe_cmd.add_argument("skill_id")

    activate_cmd = sub.add_parser("activate", help="Apply override activation")
    activate_cmd.add_argument("--capability", default=None)

    args = parser.parse_args()

    repo_root = Path.cwd()
    host_root = Path.cwd()

    if args.command == "run":
        _cmd_run(repo_root, host_root, args.skill_id, args.input)

    elif args.command == "describe":
        _cmd_describe(repo_root, args.skill_id)

    elif args.command == "activate":
        _cmd_activate(repo_root, host_root, args.capability)


def _cmd_run(repo_root: Path, host_root: Path, skill_id: str, input_json: str) -> None:
    inputs = json.loads(input_json)

    engine = _build_engine(repo_root, host_root)

    from runtime.models import ExecutionRequest

    request = ExecutionRequest(
        skill_id=skill_id,
        inputs=inputs,
    )

    result = engine.execute(request)

    print(json.dumps(result.outputs, indent=2))


def _cmd_describe(repo_root: Path, skill_id: str) -> None:
    skill_loader = YamlSkillLoader(repo_root)
    skill = skill_loader.get_skill(skill_id)

    print(json.dumps({
        "id": skill.id,
        "name": skill.name,
        "description": skill.description,
        "inputs": list(skill.inputs.keys()),
        "outputs": list(skill.outputs.keys()),
        "steps": [s.id for s in skill.steps],
    }, indent=2))


def _cmd_activate(repo_root: Path, host_root: Path, capability: str | None) -> None:
    binding_registry = BindingRegistry(repo_root, host_root)
    capability_loader = YamlCapabilityLoader(repo_root)

    service_loader = ServiceDescriptorLoader(host_root)
    override_loader = OverrideIntentLoader(host_root)
    state_store = BindingStateStore(host_root)
    quality_gate = QualityGate()

    activation = BindingActivationService(
        repo_root=repo_root,
        host_root=host_root,
        binding_registry=binding_registry,
        capability_loader=capability_loader,
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
        print(json.dumps(active, indent=2))


def _build_engine(repo_root: Path, host_root: Path) -> ExecutionEngine:
    skill_loader = YamlSkillLoader(repo_root)
    capability_loader = YamlCapabilityLoader(repo_root)

    planner = ExecutionPlanner()
    resolver = ReferenceResolver()

    binding_registry = BindingRegistry(repo_root, host_root)
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
        nested_skill_runner=NestedSkillRunner(None),  # patched below
    )

    engine.nested_skill_runner.execution_engine = engine

    return engine


if __name__ == "__main__":
    main()
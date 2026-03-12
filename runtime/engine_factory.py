from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from runtime.active_binding_map import ActiveBindingMap
from runtime.binding_executor import BindingExecutor
from runtime.binding_registry import BindingRegistry
from runtime.binding_resolver import BindingResolver
from runtime.capability_executor import DefaultCapabilityExecutor
from runtime.capability_loader import YamlCapabilityLoader
from runtime.execution_engine import ExecutionEngine
from runtime.execution_planner import ExecutionPlanner
from runtime.default_mcp_client_registry import DefaultMCPClientRegistry
from runtime.mcp_invoker import MCPInvoker
from runtime.nested_skill_runner import NestedSkillRunner
from runtime.openapi_invoker import OpenAPIInvoker
from runtime.openrpc_invoker import OpenRPCInvoker
from runtime.protocol_router import ProtocolRouter
from runtime.pythoncall_invoker import PythonCallInvoker
from runtime.reference_resolver import ReferenceResolver
from runtime.request_builder import RequestBuilder
from runtime.response_mapper import ResponseMapper
from runtime.service_resolver import ServiceResolver
from runtime.skill_loader import YamlSkillLoader


class _UnavailableMCPClientRegistry:
    def get_client(self, server: str) -> Any:
        raise RuntimeError(
            "MCP client registry is not configured. "
            "Provide a concrete registry to execute MCP bindings."
        )


@dataclass(frozen=True)
class RuntimeComponents:
    engine: ExecutionEngine
    skill_loader: YamlSkillLoader
    capability_loader: YamlCapabilityLoader
    capability_executor: DefaultCapabilityExecutor


def build_runtime_components(
    registry_root: Path,
    runtime_root: Path,
    host_root: Path,
    *,
    mcp_client_registry: Any | None = None,
) -> RuntimeComponents:
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
    mcp_invoker = MCPInvoker(
        client_registry=mcp_client_registry
        or DefaultMCPClientRegistry(fallback_registry=_UnavailableMCPClientRegistry())
    )
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

    return RuntimeComponents(
        engine=engine,
        skill_loader=skill_loader,
        capability_loader=capability_loader,
        capability_executor=capability_executor,
    )

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from runtime.active_binding_map import ActiveBindingMap
from runtime.audit import AuditRecorder
from runtime.binding_executor import BindingExecutor
from runtime.binding_registry import BindingRegistry
from runtime.binding_resolver import BindingResolver
from runtime.capability_executor import DefaultCapabilityExecutor
from runtime.capability_loader import YamlCapabilityLoader
from runtime.composite_skill_loader import CompositeSkillLoader
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
    skill_loader: YamlSkillLoader | CompositeSkillLoader
    capability_loader: YamlCapabilityLoader
    capability_executor: DefaultCapabilityExecutor


def build_runtime_components(
    registry_root: Path,
    runtime_root: Path,
    host_root: Path,
    *,
    mcp_client_registry: Any | None = None,
    local_skills_root: Path | None = None,
) -> RuntimeComponents:
    registry_skill_loader = YamlSkillLoader(registry_root)

    def _resolve_local_overlay_repo_root(path: Path) -> Path:
        # YamlSkillLoader expects repo_root containing a top-level `skills/` directory.
        # Users typically pass `<runtime>/skills/local`; convert that to `<runtime>`.
        p = path.resolve()
        if p.name == "local" and p.parent.name == "skills":
            return p.parent.parent
        if (p / "skills").is_dir():
            return p
        # Best-effort fallback: use runtime_root, which contains `skills/local` by convention.
        return runtime_root

    # If a local skills directory exists (or was explicitly provided), layer it
    # on top of the registry so local/user skills take resolution priority.
    resolved_local = local_skills_root or (runtime_root / "skills" / "local")
    if resolved_local.exists() and any(resolved_local.iterdir()):
        local_repo_root = _resolve_local_overlay_repo_root(resolved_local)
        skill_loader: YamlSkillLoader | CompositeSkillLoader = CompositeSkillLoader(
            [YamlSkillLoader(local_repo_root), registry_skill_loader]
        )
    else:
        skill_loader = registry_skill_loader

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
    audit_recorder = AuditRecorder(runtime_root)

    engine = ExecutionEngine(
        skill_loader=skill_loader,
        capability_loader=capability_loader,
        execution_planner=planner,
        reference_resolver=resolver,
        capability_executor=capability_executor,
        nested_skill_runner=NestedSkillRunner(None),
        audit_recorder=audit_recorder,
    )

    engine.nested_skill_runner.execution_engine = engine

    # Plugin discovery — load third-party extensions at startup
    from runtime.plugins import discover_all
    discovered_plugins = discover_all()

    return RuntimeComponents(
        engine=engine,
        skill_loader=skill_loader,
        capability_loader=capability_loader,
        capability_executor=capability_executor,
    )

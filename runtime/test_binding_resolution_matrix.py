from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory

from runtime.active_binding_map import ActiveBindingMap
from runtime.binding_executor import BindingExecutor
from runtime.binding_registry import BindingRegistry
from runtime.binding_resolver import BindingResolver
from runtime.capability_loader import YamlCapabilityLoader
from runtime.request_builder import RequestBuilder
from runtime.response_mapper import ResponseMapper
from runtime.service_resolver import ServiceResolver


class _DummyProtocolRouter:
    pass


def _make_executor(
    repo_root: Path, host_root: Path
) -> tuple[BindingExecutor, YamlCapabilityLoader]:
    registry_root = repo_root.parent / "agent-skill-registry"
    registry = BindingRegistry(repo_root, host_root)
    resolver = BindingResolver(registry, ActiveBindingMap(host_root))
    executor = BindingExecutor(
        binding_registry=registry,
        binding_resolver=resolver,
        service_resolver=ServiceResolver(registry),
        request_builder=RequestBuilder(),
        protocol_router=_DummyProtocolRouter(),
        response_mapper=ResponseMapper(),
    )
    loader = YamlCapabilityLoader(registry_root)
    return executor, loader


def test_environment_without_openai_prefers_python_and_avoids_openai_terminal_default() -> (
    None
):
    previous = os.environ.pop("OPENAI_API_KEY", None)
    try:
        repo_root = Path(__file__).resolve().parent.parent
        executor, loader = _make_executor(repo_root, repo_root)
        capability = loader.get_capability("evaluation.plan.validate")

        plan = executor.build_resolution_plan(capability=capability)
        chain = [item["binding_id"] for item in plan["chain"]]

        assert plan["selection_source"] == "environment_preferred"
        assert chain[0] == "python_evaluation_plan_validate"
        assert "openapi_evaluation_plan_validate_openai_chat" not in chain
    finally:
        if previous is not None:
            os.environ["OPENAI_API_KEY"] = previous


def test_environment_with_openai_prefers_openai_for_dual_binding_capability() -> None:
    previous = os.environ.get("OPENAI_API_KEY")
    os.environ["OPENAI_API_KEY"] = "test-key"
    try:
        repo_root = Path(__file__).resolve().parent.parent
        executor, loader = _make_executor(repo_root, repo_root)
        capability = loader.get_capability("evaluation.plan.validate")

        plan = executor.build_resolution_plan(capability=capability)
        chain = [item["binding_id"] for item in plan["chain"]]

        assert plan["selection_source"] == "environment_preferred"
        assert chain[0] == "openapi_evaluation_plan_validate_openai_chat"
    finally:
        if previous is None:
            os.environ.pop("OPENAI_API_KEY", None)
        else:
            os.environ["OPENAI_API_KEY"] = previous


def test_local_selection_keeps_terminal_official_default_safety_net() -> None:
    previous = os.environ.pop("OPENAI_API_KEY", None)
    try:
        repo_root = Path(__file__).resolve().parent.parent
        with TemporaryDirectory(prefix="agent-skills-host-") as tmp:
            host_root = Path(tmp)
            agent_dir = host_root / ".agent-skills"
            agent_dir.mkdir(parents=True, exist_ok=True)
            (agent_dir / "active_bindings.json").write_text(
                json.dumps(
                    {"decision.input.route": "python_decision_input_route"}, indent=2
                ),
                encoding="utf-8",
            )

            executor, loader = _make_executor(repo_root, host_root)
            capability = loader.get_capability("decision.input.route")
            plan = executor.build_resolution_plan(capability=capability)
            chain = [item["binding_id"] for item in plan["chain"]]

            assert plan["selection_source"] == "local_selection"
            assert chain[0] == "python_decision_input_route"
            assert "openapi_decision_input_route_openai_chat" in chain
    finally:
        if previous is not None:
            os.environ["OPENAI_API_KEY"] = previous

#!/usr/bin/env python3
"""
Run reusable OpenAPI binding verification scenarios.

Each scenario executes a capability through the real runtime binding pipeline,
using a local isolated active binding map and optional local mock service.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
REGISTRY_ROOT = ROOT.parent / "agent-skill-registry"
DEFAULT_SCENARIOS_DIR = Path(__file__).resolve().parent / "openapi_scenarios"

sys.path.insert(0, str(ROOT))

from runtime.active_binding_map import ActiveBindingMap  # noqa: E402
from runtime.binding_executor import BindingExecutor  # noqa: E402
from runtime.binding_resolver import BindingResolver  # noqa: E402
from runtime.binding_registry import BindingRegistry  # noqa: E402
from runtime.capability_executor import DefaultCapabilityExecutor  # noqa: E402
from runtime.capability_loader import YamlCapabilityLoader  # noqa: E402
from runtime.mcp_invoker import MCPInvoker  # noqa: E402
from runtime.openapi_invoker import OpenAPIInvoker  # noqa: E402
from runtime.openrpc_invoker import OpenRPCInvoker  # noqa: E402
from runtime.protocol_router import ProtocolRouter  # noqa: E402
from runtime.pythoncall_invoker import PythonCallInvoker  # noqa: E402
from runtime.request_builder import RequestBuilder  # noqa: E402
from runtime.response_mapper import ResponseMapper  # noqa: E402
from runtime.service_resolver import ServiceResolver  # noqa: E402

from openapi_harness.mocks import start_mock_server  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify OpenAPI bindings using reusable scenarios."
    )
    parser.add_argument(
        "--scenario",
        type=Path,
        default=None,
        help="Path to a specific scenario JSON file.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run all scenarios in tooling/openapi_scenarios.",
    )
    parser.add_argument(
        "--scenarios-dir",
        type=Path,
        default=DEFAULT_SCENARIOS_DIR,
        help="Directory containing scenario JSON files.",
    )
    parser.add_argument(
        "--report-file",
        type=Path,
        default=None,
        help="Optional path to write a JSON execution report.",
    )
    return parser.parse_args()


def _build_capability_executor(host_root: Path) -> DefaultCapabilityExecutor:
    binding_registry = BindingRegistry(ROOT, host_root)
    active_map = ActiveBindingMap(host_root)
    binding_resolver = BindingResolver(binding_registry, active_map)
    service_resolver = ServiceResolver(binding_registry)

    protocol_router = ProtocolRouter(
        openapi_invoker=OpenAPIInvoker(),
        mcp_invoker=MCPInvoker(client_registry=None),
        openrpc_invoker=OpenRPCInvoker(),
        pythoncall_invoker=PythonCallInvoker(),
    )

    binding_executor = BindingExecutor(
        binding_registry=binding_registry,
        binding_resolver=binding_resolver,
        service_resolver=service_resolver,
        request_builder=RequestBuilder(),
        protocol_router=protocol_router,
        response_mapper=ResponseMapper(),
    )

    return DefaultCapabilityExecutor(binding_executor)


def _load_scenario(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Scenario '{path}' must contain a JSON object.")
    raw["_path"] = str(path)
    return raw


def _collect_scenarios(args: argparse.Namespace) -> list[dict[str, Any]]:
    if args.scenario is not None and args.all:
        raise ValueError("Use either --scenario or --all, not both.")

    if args.scenario is not None:
        return [_load_scenario(args.scenario)]

    scenario_paths = sorted(args.scenarios_dir.glob("*.json"))
    if not scenario_paths:
        raise ValueError(f"No scenario files found in '{args.scenarios_dir}'.")

    return [_load_scenario(path) for path in scenario_paths]


def _validate_required_fields(scenario: dict[str, Any]) -> None:
    required = [
        "id",
        "capability_id",
        "binding_id",
        "input",
        "expected_output",
    ]
    missing = [field for field in required if field not in scenario]
    if missing:
        raise ValueError(
            f"Scenario '{scenario.get('_path', 'unknown')}' missing required fields: {missing}"
        )


def _run_scenario(scenario: dict[str, Any]) -> dict[str, Any]:
    _validate_required_fields(scenario)

    mock = None
    if "mock_server" in scenario:
        mock = start_mock_server(scenario["mock_server"])

    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            host_root = Path(tmp_dir)
            state_dir = host_root / ".agent-skills"
            state_dir.mkdir(parents=True, exist_ok=True)
            (state_dir / "active_bindings.json").write_text(
                json.dumps(
                    {
                        scenario["capability_id"]: scenario["binding_id"],
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )

            capability_loader = YamlCapabilityLoader(REGISTRY_ROOT)
            capability = capability_loader.get_capability(scenario["capability_id"])
            executor = _build_capability_executor(host_root)

            result = executor.execute(
                capability,
                scenario["input"],
                trace_id=scenario.get("trace_id")
                or f"openapi-scenario-{scenario['id']}",
            )

            if isinstance(result, tuple):
                outputs, meta = result
            else:
                outputs, meta = result, {}

            expected_output = scenario["expected_output"]
            if outputs != expected_output:
                return {
                    "id": scenario["id"],
                    "passed": False,
                    "reason": "Unexpected output.",
                    "outputs": outputs,
                    "expected_output": expected_output,
                    "meta": meta,
                }

            if meta.get("binding_id") != scenario["binding_id"]:
                return {
                    "id": scenario["id"],
                    "passed": False,
                    "reason": "Selected binding does not match scenario binding_id.",
                    "meta": meta,
                }

            expected_service_id = scenario.get("expected_service_id")
            if (
                expected_service_id is not None
                and meta.get("service_id") != expected_service_id
            ):
                return {
                    "id": scenario["id"],
                    "passed": False,
                    "reason": "Resolved service_id does not match expected_service_id.",
                    "meta": meta,
                }

            return {
                "id": scenario["id"],
                "passed": True,
                "outputs": outputs,
                "meta": meta,
            }
    finally:
        if mock is not None:
            mock.stop()


def main() -> int:
    args = parse_args()

    try:
        scenarios = _collect_scenarios(args)
    except Exception as e:
        print(f"Failed to load scenarios: {e}")
        return 1

    results: list[dict[str, Any]] = []
    failed = 0

    for scenario in scenarios:
        print(f"Running scenario: {scenario.get('id', 'unknown')}")
        try:
            result = _run_scenario(scenario)
        except Exception as e:
            failed += 1
            results.append(
                {
                    "id": scenario.get("id", "unknown"),
                    "passed": False,
                    "reason": f"Unhandled exception: {type(e).__name__}: {e}",
                }
            )
            continue

        results.append(result)
        if result.get("passed"):
            print("  PASS")
        else:
            failed += 1
            print(f"  FAIL: {result.get('reason')}")

    summary = {
        "total": len(results),
        "passed": len(results) - failed,
        "failed": failed,
        "results": results,
    }

    if args.report_file is not None:
        args.report_file.parent.mkdir(parents=True, exist_ok=True)
        args.report_file.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print("\nOpenAPI verification summary")
    print(
        json.dumps(
            {
                "total": summary["total"],
                "passed": summary["passed"],
                "failed": summary["failed"],
            },
            indent=2,
        )
    )

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

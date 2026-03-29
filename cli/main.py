from __future__ import annotations

import argparse
import json
import logging
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

    parser = argparse.ArgumentParser(
        prog="skills",
        description="Agent Skills Runtime — declarative AI agent skill execution engine.",
        epilog=(
            "Getting started:\n"
            "  agent-skills doctor                           Verify environment\n"
            "  agent-skills list                             List available skills\n"
            "  agent-skills run <skill_id> --input '{...}'   Execute a skill\n"
            "  agent-skills scaffold --wizard                Create a skill interactively\n"
            "\n"
            "Command groups:\n"
            "  Core:      run, ask, describe, discover, list, capabilities\n"
            "  Author:    scaffold, validate, test, check-wiring, trace,\n"
            "             explain-capability, dev, compose\n"
            "  Package:   package-prepare, package-validate, package-pr,\n"
            "             export, import, contribute\n"
            "  Community: rate, report, discover --similar\n"
            "  Operate:   serve, doctor, attach, activate, openapi\n"
            "  Bench:     benchmark, benchmark-lab\n"
            "  Admin:     gateway-diagnostics, gateway-reset-metrics,\n"
            "             skill-governance, audit-purge"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
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

    run_cmd = sub.add_parser(
        "run",
        help="Execute a skill by ID (use 'ask' if you don't know the skill ID)",
    )
    run_cmd.add_argument(
        "skill_id", help="Skill identifier (e.g. text.translate-summary)"
    )
    run_cmd.add_argument(
        "--input",
        default=None,
        help='Inline JSON object with skill inputs (e.g. \'{"text": "hello"}\')',
    )
    run_cmd.add_argument(
        "--input-file", default=None, help="Path to a JSON file with skill inputs"
    )
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

    # --- K1: ask (NL autopilot) ---
    ask_cmd = sub.add_parser(
        "ask",
        help=(
            "Natural language autopilot — describe what you need and the "
            "runtime finds and runs the right skill. Use 'run' if you "
            "already know the skill ID, or 'discover' to search without executing."
        ),
    )
    ask_cmd.add_argument(
        "question",
        help="Natural language description of what you want (e.g. 'summarize this text in Spanish')",
    )
    ask_cmd.add_argument(
        "--input",
        default=None,
        help="Inline JSON with extra inputs (merged with auto-detected inputs)",
    )
    ask_cmd.add_argument(
        "--dry-run",
        action="store_true",
        help="Show the selected skill and input mapping without executing",
    )
    ask_cmd.add_argument(
        "--top",
        type=int,
        default=1,
        help="Number of candidate skills to show (default: 1, run top match)",
    )
    ask_cmd.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON output",
    )
    add_root_args(ask_cmd)

    describe_cmd = sub.add_parser(
        "describe", help="Describe a skill (inputs, outputs, steps, capabilities)"
    )
    describe_cmd.add_argument(
        "skill_id", help="Skill identifier (e.g. text.translate-summary)"
    )
    describe_cmd.add_argument(
        "--json", action="store_true", help="Emit machine-readable JSON output"
    )
    describe_cmd.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show full detail: capabilities used, dependencies, DAG edges, and raw YAML",
    )
    add_root_args(describe_cmd)

    discover_cmd = sub.add_parser(
        "discover",
        help=(
            "Search and rank skills for an intent (read-only — does not execute). "
            "Use 'ask' to also execute the best match, or 'run' with a known skill ID."
        ),
    )
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

    capabilities_cmd = sub.add_parser(
        "capabilities", help="List registered capabilities"
    )
    capabilities_cmd.add_argument(
        "--domain",
        default=None,
        help="Filter by domain prefix (e.g. 'text', 'data', 'code')",
    )
    capabilities_cmd.add_argument(
        "--search",
        default=None,
        help="Filter by substring match on id or description",
    )
    capabilities_cmd.add_argument(
        "--json", action="store_true", help="Emit machine-readable JSON output"
    )
    add_root_args(capabilities_cmd)

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

    trace_cmd = sub.add_parser(
        "trace",
        help="Execute a skill with step-by-step event tracing (like 'run' but prints each step's lifecycle)",
    )
    trace_cmd.add_argument(
        "skill_id", help="Skill identifier (e.g. text.translate-summary)"
    )
    trace_cmd.add_argument(
        "--input", default=None, help="Inline JSON object with skill inputs"
    )
    trace_cmd.add_argument(
        "--input-file", default=None, help="Path to a JSON file with skill inputs"
    )
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

    doctor_cmd = sub.add_parser(
        "doctor",
        help="Run system health checks (use --fix to auto-clone missing registry)",
    )
    doctor_cmd.add_argument(
        "--fix",
        action="store_true",
        help="Auto-fix problems (e.g. clone missing registry)",
    )
    add_root_args(doctor_cmd)

    # --- inspect-plugins ---
    sub.add_parser(
        "inspect-plugins",
        help="List all discovered plugins and their load status",
    )

    scaffold_cmd = sub.add_parser(
        "scaffold",
        help="Generate a skill YAML from a natural-language intent description",
    )
    scaffold_cmd.add_argument(
        "intent",
        nargs="?",
        default=None,
        help="Plain-language description of the workflow to create. Omit to use --wizard mode.",
    )
    scaffold_cmd.add_argument(
        "--wizard",
        action="store_true",
        help="Interactive guided mode: answer questions to define inputs, outputs, and capabilities.",
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

    serve_cmd = sub.add_parser(
        "serve",
        help="Start the HTTP API server",
        epilog="OpenAPI spec available at http://<host>:<port>/openapi.json once running.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
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

    # ── MCP Server ──────────────────────────────────────────────────────
    mcp_serve_cmd = sub.add_parser(
        "mcp-serve",
        help="Start the MCP server (Model Context Protocol) for Claude Desktop, Cursor, VS Code Copilot",
        epilog=(
            "Exposes all runtime capabilities as MCP tools via JSON-RPC 2.0.\n\n"
            "  stdio (default): for integration with Claude Desktop, Cursor, etc.\n"
            "  sse:             for browser-based or remote MCP clients.\n\n"
            "Claude Desktop config example:\n"
            '  {"mcpServers": {"agent-skills": {"command": "agent-skills", "args": ["mcp-serve"]}}}'
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    mcp_serve_cmd.add_argument(
        "--sse",
        action="store_true",
        default=False,
        help="Use SSE transport instead of stdio (default: stdio).",
    )
    mcp_serve_cmd.add_argument(
        "--host",
        default="0.0.0.0",
        help="Bind address for SSE transport (default: 0.0.0.0).",
    )
    mcp_serve_cmd.add_argument(
        "--port",
        type=int,
        default=8765,
        help="Listen port for SSE transport (default: 8765).",
    )

    validate_cmd = sub.add_parser(
        "validate",
        help="Validate a skill YAML: check capability references, input mappings, and DAG integrity",
    )
    validate_grp = validate_cmd.add_mutually_exclusive_group()
    validate_grp.add_argument(
        "--skill",
        default=None,
        help="Validate a single skill by id (e.g. text.translate-summary).",
    )
    validate_grp.add_argument(
        "--file",
        type=Path,
        default=None,
        help="Validate a single skill.yaml file path.",
    )
    validate_cmd.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON output",
    )
    add_root_args(validate_cmd)

    benchmark_cmd = sub.add_parser(
        "benchmark",
        help="Run reproducible execution benchmarks and print paper-ready results",
    )
    benchmark_cmd.add_argument(
        "--skill",
        default=None,
        help="Benchmark a single skill (default: text.translate-summary).",
    )
    benchmark_cmd.add_argument(
        "--iterations",
        type=int,
        default=5,
        help="Number of iterations per skill (default: 5).",
    )
    benchmark_cmd.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON output",
    )
    add_root_args(benchmark_cmd)

    # --- K5: benchmark-lab (multi-protocol) ---
    benchmark_lab_cmd = sub.add_parser(
        "benchmark-lab",
        help="Compare execution across protocols/bindings for the same capability",
    )
    benchmark_lab_cmd.add_argument(
        "capability_id",
        help="Capability identifier (e.g. text.content.summarize)",
    )
    benchmark_lab_cmd.add_argument(
        "--runs",
        type=int,
        default=10,
        help="Number of runs per protocol (default: 10).",
    )
    benchmark_lab_cmd.add_argument(
        "--protocols",
        default=None,
        help="Comma-separated protocols to compare (default: all available). E.g. pythoncall,openapi,mcp",
    )
    benchmark_lab_cmd.add_argument(
        "--export",
        type=Path,
        default=None,
        help="Export results to a JSON file.",
    )
    benchmark_lab_cmd.add_argument(
        "--format",
        default="table",
        choices=["table", "markdown"],
        help="Output format: 'table' (default) or 'markdown' for copy-paste.",
    )
    benchmark_lab_cmd.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON output",
    )
    add_root_args(benchmark_lab_cmd)

    # --- K3: dev watch mode ---
    dev_cmd = sub.add_parser(
        "dev",
        help="Watch a skill for changes and auto-validate/test on save",
    )
    dev_cmd.add_argument(
        "skill_id",
        help="Skill identifier to watch (e.g. text.translate-summary)",
    )
    dev_cmd.add_argument(
        "--interval",
        type=float,
        default=1.0,
        help="Polling interval in seconds (default: 1.0).",
    )
    dev_cmd.add_argument(
        "--no-test",
        action="store_true",
        help="Skip test execution, only validate and check-wiring.",
    )
    add_root_args(dev_cmd)

    # --- M2: test ---
    test_cmd = sub.add_parser(
        "test",
        help="Test a skill: execute with fixture inputs, verify expected outputs",
    )
    test_cmd.add_argument(
        "skill_id", help="Skill identifier to test (e.g. text.translate-summary)"
    )
    test_cmd.add_argument(
        "--input",
        default=None,
        help="Inline JSON object with test inputs (alternative to --input-file).",
    )
    test_cmd.add_argument(
        "--input-file",
        type=Path,
        default=None,
        help="JSON file with test inputs. Default: test_input.json next to skill.yaml.",
    )
    test_cmd.add_argument(
        "--generate-fixture",
        action="store_true",
        help="Generate a test_input.json stub from the skill's input schema and exit.",
    )
    test_cmd.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON report.",
    )
    add_root_args(test_cmd)

    # --- M8: check-wiring ---
    check_wiring_cmd = sub.add_parser(
        "check-wiring",
        help="Check type compatibility between steps in a skill's dataflow",
    )
    check_wiring_cmd.add_argument("skill_id", help="Skill identifier to check")
    check_wiring_cmd.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON output.",
    )
    add_root_args(check_wiring_cmd)

    # --- M6: describe --mermaid is added to existing describe_cmd ---
    describe_cmd.add_argument(
        "--mermaid",
        action="store_true",
        help="Output a Mermaid diagram of the skill's step DAG.",
    )

    # --- M7: capabilities type filters ---
    capabilities_cmd.add_argument(
        "--input-type",
        default=None,
        choices=["string", "integer", "number", "boolean", "array", "object"],
        help="Filter capabilities that accept this input type.",
    )
    capabilities_cmd.add_argument(
        "--output-type",
        default=None,
        choices=["string", "integer", "number", "boolean", "array", "object"],
        help="Filter capabilities that produce this output type.",
    )

    # --- M4: export / import ---
    export_cmd = sub.add_parser(
        "export",
        help="Export a skill as a portable .skill-bundle.tar.gz",
    )
    export_cmd.add_argument("skill_id", help="Skill identifier to export")
    export_cmd.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output file path. Default: <skill_dir>/<skill_id>.skill-bundle.tar.gz",
    )
    add_root_args(export_cmd)

    import_cmd = sub.add_parser(
        "import",
        help="Import a skill from a .skill-bundle.tar.gz into local skills",
        aliases=["import-skill"],
    )
    import_cmd.add_argument("source", help="Path to .skill-bundle.tar.gz file")
    import_cmd.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON output.",
    )
    add_root_args(import_cmd)

    # --- M9: contribute ---
    contribute_cmd = sub.add_parser(
        "contribute",
        help="One-command skill contribution: prepare + validate + PR",
    )
    contribute_cmd.add_argument("skill_id", help="Skill identifier to contribute")
    contribute_cmd.add_argument(
        "--channel",
        choices=["experimental", "community"],
        default="experimental",
        help="Target channel (default: experimental).",
    )
    contribute_cmd.add_argument(
        "--draft",
        action="store_true",
        help="Create PR as draft.",
    )
    contribute_cmd.add_argument(
        "--dry-run",
        action="store_true",
        help="Run prepare + validate only, skip PR creation.",
    )
    contribute_cmd.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON output.",
    )
    add_root_args(contribute_cmd)

    # --- M10: discover --similar ---
    discover_cmd.add_argument(
        "--similar",
        default=None,
        help="Find skills similar to this skill ID (ignores intent).",
    )

    # --- M11: rate ---
    rate_cmd = sub.add_parser(
        "rate",
        help="Rate a skill (1-5 stars) with optional comment",
    )
    rate_cmd.add_argument("skill_id", help="Skill identifier to rate")
    rate_cmd.add_argument(
        "--score",
        type=int,
        required=True,
        choices=[1, 2, 3, 4, 5],
        help="Rating score (1-5)",
    )
    rate_cmd.add_argument(
        "--comment", default=None, help="Optional comment about the skill"
    )
    rate_cmd.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON output.",
    )
    add_root_args(rate_cmd)

    # --- M12: report ---
    report_cmd = sub.add_parser(
        "report",
        help="Report an issue with a skill (generates GitHub issue template)",
    )
    report_cmd.add_argument("skill_id", help="Skill identifier to report")
    report_cmd.add_argument("--issue", required=True, help="Description of the issue")
    report_cmd.add_argument(
        "--severity",
        default="medium",
        choices=["low", "medium", "high", "critical"],
        help="Issue severity (default: medium).",
    )
    report_cmd.add_argument(
        "--open-browser",
        action="store_true",
        help="Open the GitHub new-issue URL in the default browser.",
    )
    add_root_args(report_cmd)

    # --- K7: showcase ---
    showcase_cmd = sub.add_parser(
        "showcase",
        help="Generate a shareable markdown showcase for a skill (diagram + example + benchmark)",
    )
    showcase_cmd.add_argument(
        "skill_id",
        help="Skill identifier to showcase (e.g. text.summarize-plain-input)",
    )
    showcase_cmd.add_argument(
        "--no-run",
        action="store_true",
        help="Skip real execution — only emit metadata + diagram.",
    )
    showcase_cmd.add_argument(
        "--benchmark",
        action="store_true",
        help="Include a performance comparison table (runs benchmark-lab internally).",
    )
    showcase_cmd.add_argument(
        "--runs",
        type=int,
        default=5,
        help="Number of benchmark runs per binding (default: 5, requires --benchmark).",
    )
    showcase_cmd.add_argument(
        "--file",
        type=Path,
        default=None,
        help="Write the markdown to a file instead of stdout.",
    )
    add_root_args(showcase_cmd)

    # --- K6: compose ---
    compose_cmd = sub.add_parser(
        "compose",
        help="Compile a .compose DSL file into a skill.yaml (or run it directly)",
    )
    compose_cmd.add_argument(
        "source",
        help="Path to a .compose file",
    )
    compose_cmd.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Write compiled skill.yaml to this path (default: print to stdout)",
    )
    compose_cmd.add_argument(
        "--run",
        action="store_true",
        help="Compile and immediately execute the composed skill",
    )
    compose_cmd.add_argument(
        "--input",
        default=None,
        help="Inline JSON inputs for --run mode",
    )
    compose_cmd.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON output",
    )
    add_root_args(compose_cmd)

    # --- K4: triggers ---
    triggers_cmd = sub.add_parser(
        "triggers",
        help="Manage skill triggers: list, fire events, check status",
    )
    triggers_sub = triggers_cmd.add_subparsers(dest="triggers_action", required=True)

    triggers_list = triggers_sub.add_parser("list", help="List all registered triggers")
    triggers_list.add_argument(
        "--type",
        default=None,
        choices=["schedule", "event", "webhook", "file_change"],
        help="Filter by type",
    )
    triggers_list.add_argument("--json", action="store_true", help="JSON output")
    add_root_args(triggers_list)

    triggers_fire = triggers_sub.add_parser(
        "fire", help="Manually fire a trigger event"
    )
    triggers_fire.add_argument(
        "--event-type",
        default="webhook",
        choices=["webhook", "event", "file_change", "schedule"],
        help="Event type",
    )
    triggers_fire.add_argument("--webhook", default=None, help="Webhook name to fire")
    triggers_fire.add_argument(
        "--source-skill", default=None, help="Source skill for event chaining"
    )
    triggers_fire.add_argument(
        "--status", default="completed", help="Status for event chaining"
    )
    triggers_fire.add_argument(
        "--files", default=None, help="Comma-separated file paths for file_change"
    )
    triggers_fire.add_argument("--payload", default=None, help="Extra JSON payload")
    triggers_fire.add_argument("--json", action="store_true", help="JSON output")
    add_root_args(triggers_fire)

    triggers_status = triggers_sub.add_parser(
        "status", help="Show trigger registration summary"
    )
    triggers_status.add_argument("--json", action="store_true", help="JSON output")
    add_root_args(triggers_status)

    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        default=False,
        help="Enable verbose/debug output for troubleshooting.",
    )

    args = parser.parse_args()

    # Configure logging verbosity
    if getattr(args, "verbose", False):
        logging.basicConfig(
            level=logging.DEBUG, format="%(name)s %(levelname)s %(message)s"
        )
    else:
        logging.basicConfig(level=logging.WARNING)

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

    elif args.command == "ask":
        _cmd_ask(
            registry_root,
            runtime_root,
            host_root,
            args.question,
            getattr(args, "input", None),
            args.dry_run,
            args.top,
            args.json,
            local_skills_root,
        )

    elif args.command == "describe":
        _cmd_describe(
            registry_root, args.skill_id, args.json, args.verbose, args.mermaid,
            runtime_root=runtime_root,
        )

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
            getattr(args, "similar", None),
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

    elif args.command == "capabilities":
        _cmd_capabilities(
            registry_root,
            args.domain,
            args.search,
            args.json,
            getattr(args, "input_type", None),
            getattr(args, "output_type", None),
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
        _cmd_doctor(
            registry_root, runtime_root, host_root, fix=getattr(args, "fix", False)
        )

    elif args.command == "inspect-plugins":
        from runtime.plugins import discover_all, PLUGIN_GROUPS
        from runtime.plugin_protocols import validate_plugin

        print("Plugin groups:")
        all_plugins = discover_all()
        total = 0
        for group in PLUGIN_GROUPS:
            plugins = all_plugins.get(group, {})
            print(f"\n  {group}:")
            if not plugins:
                print("    (none discovered)")
            for name, obj in plugins.items():
                total += 1
                violations = validate_plugin(group, name, obj)
                status = "OK" if not violations else f"INVALID: {'; '.join(violations)}"
                print(f"    {name} → {obj}  [{status}]")
        print(f"\nTotal plugins loaded: {total}")

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
            getattr(args, "wizard", False),
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

    elif args.command == "mcp-serve":
        _cmd_mcp_serve(args)

    elif args.command == "validate":
        _cmd_validate(
            registry_root,
            getattr(args, "skill", None),
            getattr(args, "file", None),
            args.json,
        )

    elif args.command == "benchmark":
        _cmd_benchmark(
            registry_root,
            runtime_root,
            host_root,
            getattr(args, "skill", None),
            args.iterations,
            args.json,
            local_skills_root,
        )

    elif args.command == "benchmark-lab":
        _cmd_benchmark_lab(
            registry_root,
            runtime_root,
            host_root,
            args.capability_id,
            args.runs,
            getattr(args, "protocols", None),
            getattr(args, "export", None),
            args.json,
            getattr(args, "format", "table"),
            local_skills_root,
        )

    elif args.command == "dev":
        _cmd_dev(
            registry_root,
            runtime_root,
            host_root,
            args.skill_id,
            args.interval,
            args.no_test,
            local_skills_root,
        )

    elif args.command == "test":
        _cmd_test(
            registry_root,
            runtime_root,
            host_root,
            args.skill_id,
            getattr(args, "input_file", None),
            args.generate_fixture,
            args.json,
            local_skills_root,
        )

    elif args.command == "check-wiring":
        _cmd_check_wiring(
            registry_root,
            args.skill_id,
            args.json,
        )

    elif args.command == "export":
        _cmd_export(
            registry_root,
            runtime_root,
            args.skill_id,
            getattr(args, "out", None),
            local_skills_root,
        )

    elif args.command in ("import", "import-skill"):
        _cmd_import(
            registry_root,
            runtime_root,
            args.source,
            args.json,
            local_skills_root,
        )

    elif args.command == "contribute":
        _cmd_contribute(
            registry_root,
            runtime_root,
            host_root,
            args.skill_id,
            args.channel,
            args.draft,
            args.dry_run,
            args.json,
            local_skills_root,
        )

    elif args.command == "rate":
        _cmd_rate(
            runtime_root,
            args.skill_id,
            args.score,
            args.comment,
            args.json,
        )

    elif args.command == "report":
        _cmd_report(
            args.skill_id,
            args.issue,
            args.severity,
            args.open_browser,
        )

    elif args.command == "showcase":
        _cmd_showcase(
            registry_root,
            runtime_root,
            host_root,
            args.skill_id,
            no_run=args.no_run,
            include_benchmark=args.benchmark,
            benchmark_runs=args.runs,
            out_file=getattr(args, "file", None),
            local_skills_root=local_skills_root,
        )

    elif args.command == "compose":
        _cmd_compose(
            registry_root,
            runtime_root,
            host_root,
            args.source,
            getattr(args, "out", None),
            args.run,
            getattr(args, "input", None),
            args.json,
            local_skills_root,
        )

    elif args.command == "triggers":
        _cmd_triggers(
            registry_root,
            runtime_root,
            host_root,
            args.triggers_action,
            args,
            local_skills_root,
        )


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


def _cmd_mcp_serve(args):
    """Start the MCP server (Model Context Protocol).

    Delegates to ``official_mcp_servers.server.main()`` which runs the MCP
    protocol over stdio (default) or SSE transport.
    """
    try:
        from official_mcp_servers.server import main as mcp_main
    except ImportError as exc:
        print(
            "Error: MCP server requires the 'mcp' package.\n"
            "Install with: pip install 'agent-skills[mcp]'"
        )
        raise SystemExit(1) from exc

    transport = "sse" if args.sse else "stdio"
    mcp_main(transport=transport, host=args.host, port=args.port)


def _cmd_scaffold(
    registry_root: Path,
    runtime_root: Path,
    host_root: Path,
    local_skills_root: Path | None,
    intent: str | None,
    channel: str,
    model: str,
    dry_run: bool,
    out_dir: Path | None,
    wizard: bool = False,
) -> None:
    import os
    from tooling.skill_authoring import generate_test_fixture

    # --- M1: Wizard mode ---
    if wizard or not intent:
        intent, channel, wizard_inputs, wizard_outputs, wizard_caps = _scaffold_wizard(
            registry_root,
            channel,
        )

    from official_services.scaffold_service import generate_skill_from_prompt

    print(
        f"[scaffold] Generating skill for: {intent[:80]}{'...' if len(intent) > 80 else ''}"
    )
    has_key = bool(os.environ.get("OPENAI_API_KEY"))
    scaffolder_env = (
        os.environ.get("AGENT_SKILLS_SCAFFOLDER_MODE", "binding-first").strip().lower()
    )
    if scaffolder_env == "direct-openai" and has_key:
        mode_label = "LLM (direct OpenAI)"
    elif has_key:
        mode_label = (
            "binding-first (planner uses available bindings; OPENAI_API_KEY detected)"
        )
    else:
        mode_label = "template (no OPENAI_API_KEY — offline deterministic generation)"
    print(f"[scaffold] Mode: {mode_label}")

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

    # --- Generate test fixture ---
    try:
        skill_doc = yaml.safe_load(skill_yaml)
        if isinstance(skill_doc, dict):
            fixture = generate_test_fixture(skill_doc)
            test_file = target_dir / "test_input.json"
            test_file.write_text(
                json.dumps(fixture, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            print(f"[scaffold] Test fixture   : {test_file}")
    except Exception:
        pass

    # --- Auto-validate ---
    print("[scaffold] Running validation...")
    try:
        from tooling.validate_skill_schema import validate_skill_yaml

        schema_errs = validate_skill_yaml(target_file)
        if schema_errs:
            print("[scaffold] Schema issues:")
            for e in schema_errs:
                print(f"           - {e}")
        else:
            print("[scaffold] Schema         : OK")
    except Exception:
        pass

    print("[scaffold] Next steps:")
    print(f"           1. Review and edit {target_file}")
    print(f"           2. Run: agent-skills test {suggested_id}")
    print(f"           3. Run: agent-skills check-wiring {suggested_id}")
    print(f"           4. Contribute: agent-skills contribute {suggested_id}")


def _scaffold_wizard(
    registry_root: Path,
    default_channel: str,
) -> tuple[str, str, dict, dict, list[str]]:
    """Interactive wizard for skill creation. Returns (intent, channel, inputs, outputs, caps)."""
    print("=" * 60)
    print("  Skill Creation Wizard")
    print("=" * 60)
    print()

    # Step 1: Intent
    intent = input(
        "What should this skill do? (describe in plain language)\n> "
    ).strip()
    if not intent:
        print("Intent cannot be empty.")
        raise SystemExit(1)

    # Step 2: Channel
    print(f"\nTarget channel [{default_channel}]: ", end="")
    ch = input().strip()
    channel = ch if ch in ("local", "experimental", "community") else default_channel

    # Step 3: Inputs
    print(
        "\nDefine skill inputs (one per line, format: name:type — e.g. 'text:string')"
    )
    print("  Available types: string, integer, number, boolean, array, object")
    print("  Press Enter on empty line when done.")
    inputs: dict[str, dict] = {}
    while True:
        line = input("  > ").strip()
        if not line:
            break
        if ":" in line:
            name, ftype = line.split(":", 1)
            inputs[name.strip()] = {"type": ftype.strip(), "required": True}
        else:
            inputs[line] = {"type": "string", "required": True}

    if not inputs:
        inputs = {"text": {"type": "string", "required": True}}
        print("  (defaulting to: text:string)")

    # Step 4: Outputs
    print("\nDefine skill outputs (same format):")
    print("  Press Enter on empty line when done.")
    outputs: dict[str, dict] = {}
    while True:
        line = input("  > ").strip()
        if not line:
            break
        if ":" in line:
            name, ftype = line.split(":", 1)
            outputs[name.strip()] = {"type": ftype.strip()}
        else:
            outputs[line] = {"type": "string"}

    if not outputs:
        outputs = {"result": {"type": "string"}}
        print("  (defaulting to: result:string)")

    # Step 5: Capability suggestions
    print("\nSearching capabilities for your intent...")
    capability_loader = YamlCapabilityLoader(registry_root)
    all_caps = capability_loader.get_all_capabilities()

    # Simple keyword matching
    words = {w.lower() for w in intent.split() if len(w) > 2}
    scored: list[tuple[int, str]] = []
    for cap_id, cap in all_caps.items():
        desc = (getattr(cap, "description", "") or "").lower()
        score = sum(1 for w in words if w in cap_id.lower() or w in desc)
        if score > 0:
            scored.append((score, cap_id))
    scored.sort(key=lambda x: -x[0])
    top = scored[:10]

    if top:
        print(f"\nSuggested capabilities ({len(top)} matches):")
        for i, (score, cid) in enumerate(top, 1):
            desc = getattr(all_caps[cid], "description", "") or ""
            short = (desc[:60] + "...") if len(desc) > 60 else desc
            print(f"  {i:2}. {cid:<45} {short}")
    else:
        print(
            "\nNo capabilities matched your intent. The scaffolder will select automatically."
        )

    print(
        "\nWhich capabilities to use? (comma-separated numbers, or Enter for auto-select)"
    )
    selection = input("> ").strip()
    selected_caps: list[str] = []
    if selection:
        for part in selection.split(","):
            try:
                idx = int(part.strip()) - 1
                if 0 <= idx < len(top):
                    selected_caps.append(top[idx][1])
            except ValueError:
                # Maybe they typed a capability id directly
                if part.strip() in all_caps:
                    selected_caps.append(part.strip())

    if selected_caps:
        print(f"\nSelected: {', '.join(selected_caps)}")
        # Enhance intent with selection info
        intent += f" [capabilities: {', '.join(selected_caps)}]"

    print("\nGenerating skill...\n")
    return intent, channel, inputs, outputs, selected_caps


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

    if not inputs:
        print(
            "[warn] No --input or --input-file provided. "
            "Running with empty inputs — results may be meaningless.",
            file=sys.stderr,
        )

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


def _cmd_describe(
    registry_root: Path,
    skill_id: str,
    json_output: bool = False,
    verbose: bool = False,
    mermaid: bool = False,
    *,
    runtime_root: Path | None = None,
) -> None:

    registry_loader = YamlSkillLoader(registry_root)
    skill_loader = registry_loader
    if runtime_root is not None:
        local_dir = runtime_root / "skills" / "local"
        if local_dir.exists() and any(local_dir.iterdir()):
            from runtime.composite_skill_loader import CompositeSkillLoader

            skill_loader = CompositeSkillLoader(
                [YamlSkillLoader(runtime_root), registry_loader]
            )
    skill = skill_loader.get_skill(skill_id)

    # Build step details with capability references and dependencies
    steps_detail = []
    for idx, s in enumerate(skill.steps):
        step_info: dict = {"id": s.id, "uses": s.uses}
        deps = s.config.get("depends_on")
        if deps is not None:
            step_info["depends_on"] = deps
        elif idx > 0:
            step_info["depends_on"] = [skill.steps[idx - 1].id]
        else:
            step_info["depends_on"] = []
        steps_detail.append(step_info)

    # Build DAG edge list
    edges = []
    for step_info in steps_detail:
        for dep in step_info.get("depends_on", []):
            edges.append({"from": dep, "to": step_info["id"]})

    # --- M6: Mermaid DAG output ---
    if mermaid:
        from tooling.skill_authoring import generate_mermaid_dag

        raw = (
            yaml.safe_load(Path(skill.source_file).read_text(encoding="utf-8"))
            if skill.source_file
            else {}
        )
        if not raw:
            raw = {
                "id": skill.id,
                "name": skill.name,
                "steps": [],
                "inputs": {},
                "outputs": {},
            }
            for s in skill.steps:
                raw.setdefault("steps", []).append(
                    {
                        "id": s.id,
                        "uses": s.uses,
                        "config": s.config if s.config else {},
                    }
                )
            raw["inputs"] = {k: {"type": "string"} for k in skill.inputs}
            raw["outputs"] = {k: {"type": "string"} for k in skill.outputs}
        print(generate_mermaid_dag(raw))
        return

    payload: dict = {
        "id": skill.id,
        "name": skill.name,
        "description": skill.description,
        "inputs": list(skill.inputs.keys()),
        "outputs": list(skill.outputs.keys()),
        "steps": steps_detail,
        "dag_edges": edges,
    }

    if verbose and skill.source_file:
        try:
            payload["raw_yaml"] = Path(skill.source_file).read_text(encoding="utf-8")
        except OSError:
            pass

    if json_output or verbose:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return

    # Human-readable default output
    print(f"Skill: {skill.id}")
    print(f"  Name:        {skill.name}")
    desc = skill.description.strip().replace("\n", " ")
    print(f"  Description: {desc[:120]}{'...' if len(desc) > 120 else ''}")
    print(f"  Inputs:      {', '.join(skill.inputs.keys())}")
    print(f"  Outputs:     {', '.join(skill.outputs.keys())}")
    print(f"  Steps ({len(skill.steps)}):")
    for si in steps_detail:
        deps_str = ", ".join(si.get("depends_on", []))
        print(f"    {si['id']:<25} uses: {si['uses']}")
        if deps_str:
            print(f"    {'':<25} depends_on: [{deps_str}]")
    if edges:
        print(f"  DAG edges:   {' → '.join(e['from'] + '→' + e['to'] for e in edges)}")


# ---------------------------------------------------------------------------
# K1 — Ask (NL Autopilot)
# ---------------------------------------------------------------------------


def _cmd_ask(
    registry_root: Path,
    runtime_root: Path,
    host_root: Path,
    question: str,
    extra_input: str | None,
    dry_run: bool,
    top: int,
    json_output: bool,
    local_skills_root: Path | None = None,
) -> None:
    """Natural-language autopilot: discover → map inputs → execute → return."""
    gateway = SkillGateway(
        registry_root=registry_root,
        runtime_root=runtime_root,
        host_root=host_root,
        local_skills_root=local_skills_root,
    )

    # 1. Discover the best skill for this question
    results = gateway.discover(intent=question, limit=max(top, 5))

    if not results:
        if json_output:
            print(
                json.dumps(
                    {"ok": False, "error": "No skills match the question."}, indent=2
                )
            )
        else:
            print("[ask] No skills found for your question.")
        raise SystemExit(1)

    # 2. Show candidates if top > 1
    candidates = []
    if top > 1 or dry_run:
        candidates = [
            {
                "skill_id": r.skill.skill_id,
                "name": r.skill.name,
                "score": r.score,
                "reason": r.reason,
            }
            for r in results[:top]
        ]
        if not json_output:
            print(f'[ask] Question: "{question}"\n')
            print(f"[ask] Top {min(top, len(results))} candidate(s):")
            for i, c in enumerate(candidates):
                print(
                    f"  {i + 1}. {c['skill_id']:<40} score={c['score']:.4f}  {c['name']}"
                )
            print()

    # Select the best match
    best = results[0]
    skill_id = best.skill.skill_id
    skill_spec = gateway.components.skill_loader.get_skill(skill_id)

    # 3. Map inputs: extract from the question text + merge extra_input
    mapped_inputs = _ask_map_inputs(question, skill_spec, extra_input)

    if dry_run:
        plan = {
            "selected_skill": skill_id,
            "score": best.score,
            "mapped_inputs": mapped_inputs,
            "skill_inputs": {
                k: {
                    "type": getattr(v, "type", "string"),
                    "required": getattr(v, "required", False),
                }
                for k, v in skill_spec.inputs.items()
            },
        }
        if json_output:
            payload = {"ok": True, "candidates": candidates, "plan": plan}
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            print(f"[ask] Selected: {skill_id} (score={best.score:.4f})")
            print("[ask] Mapped inputs:")
            for k, v in mapped_inputs.items():
                val_str = str(v)
                if len(val_str) > 80:
                    val_str = val_str[:77] + "..."
                print(f"  {k}: {val_str}")
            print(
                f"\n[ask] Use --no-dry-run to execute, or: agent-skills run {skill_id} --input '...'"
            )
        return

    # 4. Execute
    if not json_output:
        print(f"[ask] Selected: {skill_id} (score={best.score:.4f})")
        print("[ask] Executing...\n")

    engine = _build_engine(registry_root, runtime_root, host_root, local_skills_root)
    request = ExecutionRequest(
        skill_id=skill_id,
        inputs=mapped_inputs,
        channel="ask",
    )
    result = engine.execute(request)

    output = {
        "ok": result.status == "completed",
        "skill_id": skill_id,
        "status": result.status,
        "outputs": dict(result.outputs) if result.outputs else {},
        "discovery_score": best.score,
    }

    if json_output:
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        if result.status == "completed":
            print(f"[ask] ✓ Completed via '{skill_id}'")
            for k, v in (result.outputs or {}).items():
                val_str = str(v)
                if len(val_str) > 200:
                    val_str = val_str[:197] + "..."
                print(f"  {k}: {val_str}")
        else:
            error = getattr(result, "error", None) or result.status
            print(f"[ask] ✗ Failed: {error}")
            raise SystemExit(1)


def _ask_map_inputs(
    question: str,
    skill_spec,
    extra_input_json: str | None,
) -> dict:
    """Map a natural-language question to a skill's required inputs.

    Strategy:
    - For string inputs named 'text', 'content', 'query', 'input', 'prompt': use the question itself
    - For 'target_language', 'language', 'lang': try to detect from question
    - For integer/number inputs with defaults: use defaults
    - Merge any explicit --input JSON on top
    """
    inputs: dict = {}

    # Well-known string field names that should receive the question text
    text_field_names = {
        "text",
        "content",
        "query",
        "input",
        "prompt",
        "message",
        "source_text",
        "body",
    }
    lang_field_names = {"target_language", "language", "lang", "locale"}

    for name, field in skill_spec.inputs.items():
        ftype = getattr(field, "type", "string")
        required = getattr(field, "required", False)

        if ftype == "string":
            lower_name = name.lower()
            if lower_name in text_field_names:
                inputs[name] = question
            elif lower_name in lang_field_names:
                lang = _ask_detect_language(question)
                if lang:
                    inputs[name] = lang
                elif required:
                    inputs[name] = "en"
            elif required:
                inputs[name] = question  # fallback: pass the question
        elif ftype == "integer":
            if required:
                inputs[name] = 10  # reasonable default
        elif ftype == "number":
            if required:
                inputs[name] = 1.0
        elif ftype == "boolean":
            if required:
                inputs[name] = True
        elif ftype == "array":
            if required:
                inputs[name] = [question]
        elif ftype == "object":
            if required:
                inputs[name] = {"value": question}

    # Merge explicit extra inputs (override auto-mapped values)
    if extra_input_json:
        try:
            extra = json.loads(extra_input_json)
            if isinstance(extra, dict):
                inputs.update(extra)
        except json.JSONDecodeError:
            pass

    return inputs


_LANG_HINTS: dict[str, str] = {
    "spanish": "es",
    "español": "es",
    "espanol": "es",
    "french": "fr",
    "français": "fr",
    "francais": "fr",
    "german": "de",
    "deutsch": "de",
    "italian": "it",
    "italiano": "it",
    "portuguese": "pt",
    "português": "pt",
    "portugues": "pt",
    "chinese": "zh",
    "mandarin": "zh",
    "japanese": "ja",
    "korean": "ko",
    "russian": "ru",
    "arabic": "ar",
    "english": "en",
    "dutch": "nl",
    "swedish": "sv",
}


def _ask_detect_language(question: str) -> str | None:
    """Try to detect a target language hint from the question text."""
    lower = question.lower()
    for hint, code in _LANG_HINTS.items():
        if hint in lower:
            return code
    # Check for "in <lang>" or "to <lang>" patterns
    for word in ["in", "to", "al", "en", "au"]:
        for hint, code in _LANG_HINTS.items():
            if f" {word} {hint}" in lower:
                return code
    return None


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
    similar: str | None = None,
) -> None:
    # --- M10: similar skills discovery ---
    if similar:
        from tooling.skill_authoring import find_similar_skills

        # Load all skills as raw dicts for comparison
        skills_root = registry_root / "skills"
        all_skills: dict[str, dict] = {}
        if skills_root.exists():
            for sf in skills_root.glob("**/skill.yaml"):
                try:
                    raw = yaml.safe_load(sf.read_text(encoding="utf-8"))
                    if isinstance(raw, dict) and raw.get("id"):
                        all_skills[raw["id"]] = raw
                except Exception:
                    pass
        # Also check local skills
        local_root = local_skills_root or (runtime_root / "skills" / "local")
        if local_root.exists():
            for sf in local_root.glob("**/skill.yaml"):
                try:
                    raw = yaml.safe_load(sf.read_text(encoding="utf-8"))
                    if isinstance(raw, dict) and raw.get("id"):
                        all_skills[raw["id"]] = raw
                except Exception:
                    pass

        results = find_similar_skills(similar, all_skills, top_n=limit)

        if json_output:
            print(
                json.dumps(
                    {"query_skill": similar, "similar": results},
                    indent=2,
                    ensure_ascii=False,
                )
            )
            return

        if not results:
            print(f"No skills similar to '{similar}' found.")
            return

        print(f"Skills similar to '{similar}':\n")
        for r in results:
            shared = ", ".join(r.get("shared_capabilities", [])[:3]) or "(none)"
            tags = ", ".join(r.get("shared_tags", [])[:3]) or "(none)"
            print(f"  {r['skill_id']:<40} similarity: {r['similarity']:.2f}")
            print(f"    {r.get('name', '')}")
            print(f"    shared capabilities: {shared}")
            print(f"    shared tags: {tags}")
            print()
        return

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

    # Human-readable table
    skills = results
    if not skills:
        print("No skills found.")
        return
    # Group by domain
    by_domain: dict[str, list] = {}
    for s in skills:
        d = s.to_dict()
        dom = d.get("domain") or (
            d["id"].split(".")[0] if "." in d["id"] else "(other)"
        )
        by_domain.setdefault(dom, []).append(d)

    print(f"Skills: {len(skills)} total ({len(by_domain)} domains)\n")
    for dom in sorted(by_domain):
        print(f"  {dom}/ ({len(by_domain[dom])})")
        for d in sorted(by_domain[dom], key=lambda x: x["id"]):
            desc = (d.get("description") or "").replace("\n", " ").strip()
            short = (desc[:55] + "...") if len(desc) > 55 else desc
            print(f"    {d['id']:<40} {short}")
        print()


def _cmd_capabilities(
    registry_root: Path,
    domain: str | None,
    search: str | None,
    json_output: bool,
    input_type: str | None = None,
    output_type: str | None = None,
) -> None:
    capability_loader = YamlCapabilityLoader(registry_root)
    all_caps = capability_loader.get_all_capabilities()

    # --- M7: Type-based filtering ---
    if input_type or output_type:
        from tooling.skill_authoring import filter_capabilities_by_type

        type_filtered = filter_capabilities_by_type(all_caps, input_type, output_type)
        type_filtered_ids = {c.id for c in type_filtered}
    else:
        type_filtered_ids = None

    caps = []
    for cap_id, cap in sorted(all_caps.items()):
        if domain and not cap_id.startswith(domain + "."):
            continue
        if search:
            term = search.lower()
            desc = getattr(cap, "description", "") or ""
            if term not in cap_id.lower() and term not in desc.lower():
                continue
        if type_filtered_ids is not None and cap_id not in type_filtered_ids:
            continue
        caps.append(cap)

    if json_output:
        payload = {
            "count": len(caps),
            "capabilities": [
                {
                    "id": c.id,
                    "description": getattr(c, "description", ""),
                    "inputs": list(getattr(c, "inputs", {}).keys()),
                    "outputs": list(getattr(c, "outputs", {}).keys()),
                    "status": (getattr(c, "metadata", None) or {}).get(
                        "status", "unknown"
                    )
                    if isinstance(getattr(c, "metadata", None), dict)
                    else "unknown",
                }
                for c in caps
            ],
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return

    # Group by domain
    domains: dict[str, list] = {}
    for c in caps:
        d = c.id.split(".")[0] if "." in c.id else "(other)"
        domains.setdefault(d, []).append(c)

    print(f"Capabilities: {len(caps)} total ({len(domains)} domains)\n")
    for d in sorted(domains):
        print(f"  {d}/ ({len(domains[d])})")
        for c in sorted(domains[d], key=lambda x: x.id):
            desc = getattr(c, "description", "") or ""
            short = (desc[:60] + "...") if len(desc) > 60 else desc
            inputs = list(getattr(c, "inputs", {}).keys())
            print(f"    {c.id:<45} {short}")
            if inputs:
                print(f"      inputs: {', '.join(inputs)}")
        print()


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


def _cmd_doctor(
    registry_root: Path, runtime_root: Path, host_root: Path, *, fix: bool = False
) -> None:

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
        if fix:
            print(f"[FIX] Cloning agent-skill-registry into {registry_root}...")
            import subprocess

            result = subprocess.run(
                [
                    "git",
                    "clone",
                    "https://github.com/gfernandf/agent-skill-registry.git",
                    str(registry_root),
                ],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                ok(f"registry cloned to {registry_root}")
            else:
                error(f"failed to clone registry: {result.stderr.strip()}")
        else:
            error(
                f"registry root not found: {registry_root}\n"
                f"       Run 'agent-skills doctor --fix' to clone it automatically,\n"
                f"       or: git clone https://github.com/gfernandf/agent-skill-registry.git {registry_root}"
            )

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


def _cmd_validate(
    registry_root: Path,
    skill_filter: str | None,
    skill_file: Path | None,
    json_output: bool,
) -> None:
    """Validate skill YAML: schema + capability references + input mappings + DAG integrity."""
    from tooling.validate_skills_deep import validate_all
    from tooling.validate_skill_schema import validate_skill_yaml

    resolved_file: Path | None = None

    if skill_file is not None:
        resolved_file = skill_file
        try:
            raw = yaml.safe_load(skill_file.read_text(encoding="utf-8"))
        except Exception as exc:
            print(json.dumps({"ok": False, "errors": [str(exc)]}, indent=2))
            raise SystemExit(1)
        skill_filter = raw.get("id")

    # --- Phase 1: JSON Schema validation ---
    schema_issues: list[dict] = []
    if resolved_file:
        schema_files = [resolved_file]
    elif skill_filter:
        # Find the specific skill file
        skills_root = registry_root / "skills"
        schema_files = [
            f
            for f in skills_root.glob("**/skill.yaml")
            if _skill_file_matches_id(f, skill_filter)
        ]
    else:
        skills_root = registry_root / "skills"
        schema_files = (
            sorted(skills_root.glob("**/skill.yaml")) if skills_root.exists() else []
        )

    for sf in schema_files:
        errs = validate_skill_yaml(sf)
        for e in errs:
            schema_issues.append(
                {
                    "level": "error",
                    "skill": str(sf.relative_to(registry_root))
                    if sf.is_relative_to(registry_root)
                    else str(sf),
                    "message": f"[schema] {e}",
                    "phase": "schema",
                }
            )

    # --- Phase 2: Deep validation (uses, wiring, DAG) ---
    deep_issues = validate_all(registry_root, skill_filter=skill_filter)
    for issue in deep_issues:
        issue["phase"] = "deep"

    all_issues = schema_issues + deep_issues
    errors = [i for i in all_issues if i["level"] == "error"]
    warnings = [i for i in all_issues if i["level"] == "warning"]

    if json_output:
        print(
            json.dumps(
                {
                    "ok": len(errors) == 0,
                    "errors": errors,
                    "warnings": warnings,
                    "phases": ["schema", "deep"],
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        if not all_issues:
            print(
                "[OK] All validations passed (schema + capability refs + DAG integrity)"
            )
        else:
            for issue in all_issues:
                tag = "ERROR" if issue["level"] == "error" else "WARN"
                skill = issue.get("skill") or "(global)"
                print(f"[{tag}] {skill}: {issue['message']}")
        print()
        print(f"Validation complete: {len(errors)} errors, {len(warnings)} warnings")
        print(f"  Schema checks: {len(schema_files)} files")
        print("  Deep checks:   uses refs, input mappings, DAG integrity")

    if errors:
        raise SystemExit(1)


def _skill_file_matches_id(filepath: Path, skill_id: str) -> bool:
    """Check if a skill.yaml file contains the given skill id."""
    try:
        raw = yaml.safe_load(filepath.read_text(encoding="utf-8"))
        return isinstance(raw, dict) and raw.get("id") == skill_id
    except Exception:
        return False


def _cmd_benchmark(
    registry_root: Path,
    runtime_root: Path,
    host_root: Path,
    skill_id: str | None,
    iterations: int,
    json_output: bool,
    local_skills_root: Path | None = None,
) -> None:
    """Run reproducible execution benchmarks."""
    import time
    import statistics

    skill_id = skill_id or "text.translate-summary"
    engine = _build_engine(registry_root, runtime_root, host_root, local_skills_root)

    # Simple default input
    inputs = {
        "text": "Agent Skills Runtime is a deterministic execution engine.",
        "target_language": "es",
    }

    timings: list[float] = []
    for i in range(iterations):
        request = ExecutionRequest(
            skill_id=skill_id,
            inputs=inputs,
            options=ExecutionOptions(),
            channel="benchmark",
        )
        t0 = time.perf_counter()
        engine.execute(request)
        elapsed = (time.perf_counter() - t0) * 1000
        timings.append(elapsed)

    result = {
        "skill": skill_id,
        "iterations": iterations,
        "mean_ms": round(statistics.mean(timings), 1),
        "median_ms": round(statistics.median(timings), 1),
        "p95_ms": round(sorted(timings)[int(len(timings) * 0.95)], 1)
        if len(timings) >= 2
        else round(timings[0], 1),
        "cold_start_ms": round(timings[0], 1),
        "timings_ms": [round(t, 1) for t in timings],
    }

    if json_output:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"Benchmark: {skill_id} ({iterations} iterations)")
        print(f"  Mean:       {result['mean_ms']:>8.1f} ms")
        print(f"  Median:     {result['median_ms']:>8.1f} ms")
        print(f"  P95:        {result['p95_ms']:>8.1f} ms")
        print(f"  Cold start: {result['cold_start_ms']:>8.1f} ms")


# ---------------------------------------------------------------------------
# K5 — Benchmark Lab (multi-protocol comparison)
# ---------------------------------------------------------------------------


def _cmd_benchmark_lab(
    registry_root: Path,
    runtime_root: Path,
    host_root: Path,
    capability_id: str,
    runs: int,
    protocols_filter: str | None,
    export_path: Path | None,
    json_output: bool,
    output_format: str = "table",
    local_skills_root: Path | None = None,
) -> dict | None:
    """Compare execution of the same capability across all available bindings/protocols."""
    import statistics
    import time

    from runtime.binding_registry import BindingRegistry
    from runtime.binding_models import InvocationRequest
    from runtime.service_resolver import ServiceResolver
    from runtime.request_builder import RequestBuilder
    from runtime.response_mapper import ResponseMapper
    from runtime.protocol_router import ProtocolRouter
    from runtime.openapi_invoker import OpenAPIInvoker
    from runtime.mcp_invoker import MCPInvoker
    from runtime.openrpc_invoker import OpenRPCInvoker
    from runtime.pythoncall_invoker import PythonCallInvoker
    from runtime.default_mcp_client_registry import DefaultMCPClientRegistry
    from runtime.capability_loader import YamlCapabilityLoader

    # Load the capability spec + generate a synthetic input
    cap_loader = YamlCapabilityLoader(registry_root)
    cap = cap_loader.get_capability(capability_id)
    test_input = _benchmark_lab_build_input(cap)

    # Build binding infra
    binding_registry = BindingRegistry(runtime_root, host_root)
    service_resolver = ServiceResolver(binding_registry)
    request_builder = RequestBuilder()
    response_mapper = ResponseMapper()

    mcp_client_registry = DefaultMCPClientRegistry(
        fallback_registry=type(
            "_",
            (),
            {
                "get_client": staticmethod(
                    lambda s: (_ for _ in ()).throw(
                        RuntimeError(f"MCP unavailable for {s}")
                    )
                )
            },
        )()
    )
    protocol_router = ProtocolRouter(
        openapi_invoker=OpenAPIInvoker(),
        mcp_invoker=MCPInvoker(client_registry=mcp_client_registry),
        openrpc_invoker=OpenRPCInvoker(),
        pythoncall_invoker=PythonCallInvoker(),
    )

    # Discover available bindings for this capability
    bindings = binding_registry.get_bindings_for_capability(capability_id)

    if not bindings:
        print(f"[benchmark-lab] No bindings found for capability '{capability_id}'.")
        raise SystemExit(1)

    # Filter by protocol if requested
    allowed_protocols = None
    if protocols_filter:
        allowed_protocols = {p.strip().lower() for p in protocols_filter.split(",")}
        bindings = [b for b in bindings if b.protocol.lower() in allowed_protocols]
        if not bindings:
            print(f"[benchmark-lab] No bindings match protocols: {protocols_filter}")
            raise SystemExit(1)

    if not json_output:
        print(f"[benchmark-lab] Capability: {capability_id}")
        print(f"[benchmark-lab] Bindings found: {len(bindings)}")
        print(f"[benchmark-lab] Runs per binding: {runs}")
        print()

    results = []
    reference_output = None

    for binding in bindings:
        binding_id = binding.id
        protocol = binding.protocol

        try:
            service = service_resolver.resolve(binding.service_id)
        except Exception as exc:
            results.append(
                {
                    "binding_id": binding_id,
                    "protocol": protocol,
                    "service_id": binding.service_id,
                    "status": "error",
                    "error": f"Service resolution failed: {exc}",
                }
            )
            continue

        timings: list[float] = []
        last_output = None
        errors = 0

        for _ in range(runs):
            try:
                payload = request_builder.build(binding=binding, step_input=test_input)
                invocation = InvocationRequest(
                    protocol=binding.protocol,
                    service=service,
                    binding=binding,
                    operation_id=binding.operation_id,
                    payload=payload,
                    context_metadata={
                        "capability_id": capability_id,
                        "binding_id": binding.id,
                        "service_id": service.id,
                    },
                )
                t0 = time.perf_counter()
                response = protocol_router.invoke(invocation)
                elapsed = (time.perf_counter() - t0) * 1000
                timings.append(elapsed)

                last_output = response_mapper.map(
                    binding=binding, invocation_response=response
                )
            except Exception:
                errors += 1

        if not timings:
            results.append(
                {
                    "binding_id": binding_id,
                    "protocol": protocol,
                    "service_id": binding.service_id,
                    "status": "all_failed",
                    "errors": errors,
                }
            )
            continue

        # Compare outputs
        if reference_output is None:
            reference_output = last_output
            output_match = True
        else:
            output_match = _benchmark_lab_outputs_match(reference_output, last_output)

        entry = {
            "binding_id": binding_id,
            "protocol": protocol,
            "service_id": binding.service_id,
            "status": "ok",
            "runs": len(timings),
            "errors": errors,
            "mean_ms": round(statistics.mean(timings), 2),
            "median_ms": round(statistics.median(timings), 2),
            "p95_ms": round(sorted(timings)[int(len(timings) * 0.95)], 2)
            if len(timings) >= 2
            else round(timings[0], 2),
            "min_ms": round(min(timings), 2),
            "max_ms": round(max(timings), 2),
            "cold_start_ms": round(timings[0], 2),
            "output_match": output_match,
        }
        results.append(entry)

    report = {
        "capability_id": capability_id,
        "runs_per_binding": runs,
        "test_input": test_input,
        "bindings": results,
    }

    if export_path:
        export_path.parent.mkdir(parents=True, exist_ok=True)
        export_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

    if json_output:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    elif output_format == "markdown":
        print(_format_benchmark_markdown(capability_id, results))
    else:
        # Pretty table
        header = f"{'Binding':<40} {'Proto':<12} {'Mean':>8} {'Median':>8} {'P95':>8} {'Match':>6} {'Err':>4}"
        print(header)
        print("─" * len(header))
        for r in results:
            if r["status"] != "ok":
                print(
                    f"{r['binding_id']:<40} {r['protocol']:<12} {'FAILED':>8} {'—':>8} {'—':>8} {'—':>6} {r.get('errors', '?'):>4}"
                )
            else:
                match_str = "✓" if r["output_match"] else "✗"
                print(
                    f"{r['binding_id']:<40} {r['protocol']:<12} "
                    f"{r['mean_ms']:>7.1f}{'ms':} {r['median_ms']:>7.1f}{'ms':} "
                    f"{r['p95_ms']:>7.1f}{'ms':} {match_str:>6} {r['errors']:>4}"
                )
        print()
        if export_path:
            print(f"[benchmark-lab] Exported: {export_path}")

    return report


def _benchmark_lab_build_input(cap) -> dict:
    """Build a synthetic test input from a capability spec."""
    inputs: dict = {}
    for name, field in (getattr(cap, "inputs", {}) or {}).items():
        ftype = getattr(field, "type", "string")
        if ftype == "string":
            inputs[name] = f"benchmark test value for {name}"
        elif ftype == "integer":
            inputs[name] = 42
        elif ftype == "number":
            inputs[name] = 3.14
        elif ftype == "boolean":
            inputs[name] = True
        elif ftype == "array":
            inputs[name] = ["item1", "item2"]
        elif ftype == "object":
            inputs[name] = {"key": "value"}
        else:
            inputs[name] = f"test_{name}"
    return inputs


def _benchmark_lab_outputs_match(ref: dict | None, current: dict | None) -> bool:
    """Loosely compare two output dicts — same keys present."""
    if ref is None or current is None:
        return ref is None and current is None
    return set(ref.keys()) == set(current.keys())


def _format_benchmark_markdown(capability_id: str, results: list[dict]) -> str:
    """Format benchmark results as a markdown table."""
    lines = [
        f"### Performance — `{capability_id}`",
        "",
        "| Binding | Protocol | Mean | Median | P95 | Match |",
        "|---------|----------|-----:|-------:|----:|:-----:|",
    ]
    for r in results:
        if r["status"] != "ok":
            lines.append(
                f"| {r['binding_id']} | {r['protocol']} | FAILED | — | — | — |"
            )
        else:
            match_str = "✓" if r["output_match"] else "✗"
            lines.append(
                f"| {r['binding_id']} | {r['protocol']} "
                f"| {r['mean_ms']:.1f} ms | {r['median_ms']:.1f} ms "
                f"| {r['p95_ms']:.1f} ms | {match_str} |"
            )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# K7 — Showcase
# ---------------------------------------------------------------------------


def _cmd_showcase(
    registry_root: Path,
    runtime_root: Path,
    host_root: Path,
    skill_id: str,
    no_run: bool = False,
    include_benchmark: bool = False,
    benchmark_runs: int = 5,
    out_file: Path | None = None,
    local_skills_root: Path | None = None,
) -> None:
    """Generate a shareable markdown showcase for a skill."""
    import io
    from contextlib import redirect_stdout
    from tooling.skill_authoring import generate_mermaid_dag, generate_test_fixture

    components = build_runtime_components(
        registry_root=registry_root,
        runtime_root=runtime_root,
        host_root=host_root,
        mcp_client_registry=None,
        local_skills_root=local_skills_root,
    )
    skill = components.skill_loader.get_skill(skill_id)

    # ----- Header -----
    md = io.StringIO()
    md.write(f"## {skill.id} — {skill.name}\n\n")
    if skill.description:
        desc = skill.description.strip().replace("\n", " ")
        md.write(f"> {desc}\n\n")

    # ----- Mermaid diagram -----
    raw = None
    if skill.source_file:
        raw = yaml.safe_load(Path(skill.source_file).read_text(encoding="utf-8"))
    if not raw:
        raw = {
            "id": skill.id,
            "name": skill.name,
            "steps": [],
            "inputs": {},
            "outputs": {},
        }
        for s in skill.steps:
            raw.setdefault("steps", []).append(
                {
                    "id": s.id,
                    "uses": s.uses,
                    "config": s.config if s.config else {},
                }
            )
        raw["inputs"] = {k: {"type": "string"} for k in skill.inputs}
        raw["outputs"] = {k: {"type": "string"} for k in skill.outputs}

    mermaid_code = generate_mermaid_dag(raw)
    md.write("### Pipeline\n\n")
    md.write(f"```mermaid\n{mermaid_code}\n```\n\n")

    # ----- Skill metadata -----
    md.write("### Inputs / Outputs\n\n")
    md.write("| Field | Direction | Type |\n")
    md.write("|-------|-----------|------|\n")
    for k, v in skill.inputs.items():
        ftype = getattr(v, "type", "string")
        md.write(f"| `{k}` | input | `{ftype}` |\n")
    for k, v in skill.outputs.items():
        ftype = getattr(v, "type", "string")
        md.write(f"| `{k}` | output | `{ftype}` |\n")
    md.write("\n")

    # ----- Example execution -----
    if not no_run:
        # Build skill_doc for fixture generation
        skill_doc = {"id": skill.id, "inputs": {}, "outputs": {}}
        for k, v in skill.inputs.items():
            skill_doc["inputs"][k] = {
                "type": getattr(v, "type", "string"),
                "required": getattr(v, "required", False),
            }
        for k, v in skill.outputs.items():
            skill_doc["outputs"][k] = {"type": getattr(v, "type", "string")}

        # Resolve test inputs
        candidate = None
        if skill.source_file:
            candidate = Path(skill.source_file).parent / "test_input.json"
        if candidate and candidate.exists():
            inputs = json.loads(candidate.read_text(encoding="utf-8"))
        else:
            inputs = generate_test_fixture(skill_doc)

        request = ExecutionRequest(
            skill_id=skill_id,
            inputs=inputs,
            channel="showcase",
        )
        result = components.engine.execute(request)

        md.write("### Example\n\n")
        md.write("**Input:**\n\n")
        md.write(
            f"```json\n{json.dumps(inputs, indent=2, ensure_ascii=False)}\n```\n\n"
        )
        md.write("**Output:**\n\n")
        outputs = dict(result.outputs) if result.outputs else {}
        md.write(
            f"```json\n{json.dumps(outputs, indent=2, ensure_ascii=False)}\n```\n\n"
        )

    # ----- Benchmark -----
    if include_benchmark:
        # Collect capabilities used by this skill
        cap_ids = list({s.uses for s in skill.steps if s.uses})
        for cap_id in cap_ids:
            bench_buf = io.StringIO()
            with redirect_stdout(bench_buf):
                report = _cmd_benchmark_lab(
                    registry_root,
                    runtime_root,
                    host_root,
                    cap_id,
                    benchmark_runs,
                    protocols_filter=None,
                    export_path=None,
                    json_output=True,
                    output_format="table",
                    local_skills_root=local_skills_root,
                )
            if report and report.get("bindings"):
                md.write(_format_benchmark_markdown(cap_id, report["bindings"]))
                md.write("\n\n")

    # ----- Try-it footer -----
    input_example = "{...}"
    if not no_run:
        compact = json.dumps(inputs, ensure_ascii=False)
        if len(compact) < 120:
            input_example = compact

    md.write("### Try it\n\n")
    md.write("```bash\n")
    md.write('pip install -e ".[all]"\n')
    md.write(f"agent-skills run {skill_id} --input '{input_example}'\n")
    md.write("```\n")

    # ----- Output -----
    content = md.getvalue()
    if out_file:
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text(content, encoding="utf-8")
        print(f"[showcase] Written to {out_file}")
    else:
        print(content)


def _cmd_dev(
    registry_root: Path,
    runtime_root: Path,
    host_root: Path,
    skill_id: str,
    interval: float,
    no_test: bool,
    local_skills_root: Path | None = None,
) -> None:
    """Watch a skill for changes and auto-validate + check-wiring + test on each save."""
    import hashlib
    import time

    from runtime.skill_loader import YamlSkillLoader
    from runtime.capability_loader import YamlCapabilityLoader
    from tooling.validate_skill_schema import validate_skill_yaml
    from tooling.skill_authoring import (
        check_wiring,
        generate_test_fixture,
        run_skill_test,
    )

    # Locate the skill file
    loader = YamlSkillLoader(registry_root)
    try:
        skill = loader.get_skill(skill_id)
    except Exception as exc:
        print(f"[dev] ERROR: Could not load skill '{skill_id}': {exc}")
        raise SystemExit(1)

    if not skill.source_file:
        print(f"[dev] ERROR: Skill '{skill_id}' has no source file on disk.")
        raise SystemExit(1)

    skill_path = Path(skill.source_file)
    watch_dir = skill_path.parent
    _watch_files = list(watch_dir.glob("*.yaml")) + list(watch_dir.glob("*.json"))

    print(f"[dev] Watching skill: {skill_id}")
    print(f"[dev] Directory: {watch_dir}")
    print(f"[dev] Interval: {interval}s | Tests: {'off' if no_test else 'on'}")
    print("[dev] Press Ctrl+C to stop\n")

    def _file_hash(path: Path) -> str:
        try:
            return hashlib.md5(path.read_bytes()).hexdigest()
        except Exception:
            return ""

    def _get_snapshot() -> dict[str, str]:
        snapshot = {}
        for f in watch_dir.glob("*.yaml"):
            snapshot[str(f)] = _file_hash(f)
        for f in watch_dir.glob("*.json"):
            snapshot[str(f)] = _file_hash(f)
        return snapshot

    def _run_cycle(cycle_num: int) -> None:
        """Run the full validate → check-wiring → test cycle."""
        timestamp = time.strftime("%H:%M:%S")
        print(f"[{timestamp}] ── Cycle {cycle_num} ──")

        # Phase 1: Schema validation
        schema_errors = validate_skill_yaml(skill_path)
        if schema_errors:
            for err in schema_errors:
                print(f"  [SCHEMA] {err}")
            print(f"  ✗ Schema validation failed ({len(schema_errors)} errors)")
            return
        print("  ✓ Schema OK")

        # Phase 2: Check wiring
        try:
            cap_loader = YamlCapabilityLoader(registry_root)
            capabilities = cap_loader.get_all_capabilities()

            raw = yaml.safe_load(skill_path.read_text(encoding="utf-8"))
            skill_doc = {
                "id": raw.get("id", skill_id),
                "inputs": raw.get("inputs", {}),
                "outputs": raw.get("outputs", {}),
                "steps": raw.get("steps", []),
            }

            wiring_issues = check_wiring(skill_doc, capabilities)
            if wiring_issues:
                for issue in wiring_issues:
                    tag = issue.get("level", "warn").upper()
                    print(f"  [{tag}] step '{issue['step']}': {issue['message']}")
                print(f"  ✗ Wiring: {len(wiring_issues)} issue(s)")
            else:
                print("  ✓ Wiring OK")
        except Exception as exc:
            print(f"  ✗ Wiring check error: {exc}")
            wiring_issues = [{"error": str(exc)}]

        # Phase 3: Test execution (optional)
        if not no_test:
            try:
                engine = _build_engine(
                    registry_root, runtime_root, host_root, local_skills_root
                )

                # Load or generate test input
                test_input_file = watch_dir / "test_input.json"
                if test_input_file.exists():
                    test_inputs = json.loads(
                        test_input_file.read_text(encoding="utf-8")
                    )
                else:
                    test_inputs = generate_test_fixture(skill_doc)

                report = run_skill_test(
                    engine=engine, skill_doc=skill_doc, inputs=test_inputs
                )
                if report["ok"]:
                    print(
                        f"  ✓ Test PASS ({report['duration_ms']}ms, {report.get('steps_executed', '?')} steps)"
                    )
                else:
                    err = report.get("error", "unknown")
                    print(f"  ✗ Test FAIL: {err} ({report['duration_ms']}ms)")
            except Exception as exc:
                print(f"  ✗ Test error: {exc}")

        print()

    # Initial run
    _run_cycle(0)
    last_snapshot = _get_snapshot()
    cycle = 1

    try:
        while True:
            time.sleep(interval)
            current = _get_snapshot()
            if current != last_snapshot:
                changed = [k for k in current if current.get(k) != last_snapshot.get(k)]
                names = ", ".join(Path(c).name for c in changed[:3])
                if len(changed) > 3:
                    names += f" +{len(changed) - 3} more"
                print(f"[dev] Change detected: {names}")
                _run_cycle(cycle)
                last_snapshot = current
                cycle += 1
    except KeyboardInterrupt:
        print("\n[dev] Stopped.")


# ---------------------------------------------------------------------------
# M2 — Test a skill
# ---------------------------------------------------------------------------


def _cmd_test(
    registry_root: Path,
    runtime_root: Path,
    host_root: Path,
    skill_id: str,
    input_file: Path | None,
    generate_fixture: bool,
    json_output: bool,
    local_skills_root: Path | None = None,
) -> None:
    """Test a skill: execute with fixture, verify expected outputs."""
    from tooling.skill_authoring import generate_test_fixture, run_skill_test

    # Load skill document (registry + local skills)
    registry_loader = YamlSkillLoader(registry_root)
    skill_loader = registry_loader
    local_dir = runtime_root / "skills" / "local"
    if local_dir.exists() and any(local_dir.iterdir()):
        from runtime.composite_skill_loader import CompositeSkillLoader

        skill_loader = CompositeSkillLoader(
            [YamlSkillLoader(runtime_root), registry_loader]
        )
    skill = skill_loader.get_skill(skill_id)
    skill_doc = {"id": skill.id, "inputs": {}, "outputs": {}, "steps": []}
    for k, v in skill.inputs.items():
        skill_doc["inputs"][k] = {
            "type": getattr(v, "type", "string"),
            "required": getattr(v, "required", False),
        }
    for k, v in skill.outputs.items():
        skill_doc["outputs"][k] = {
            "type": getattr(v, "type", "string"),
            "required": getattr(v, "required", False),
        }

    # Generate fixture mode
    if generate_fixture:
        fixture = generate_test_fixture(skill_doc)
        # Determine where to write
        if skill.source_file:
            out = Path(skill.source_file).parent / "test_input.json"
        else:
            out = runtime_root / "test_inputs" / f"{skill_id.replace('.', '_')}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(fixture, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        if json_output:
            print(
                json.dumps({"ok": True, "file": str(out), "fixture": fixture}, indent=2)
            )
        else:
            print(f"[test] Generated test fixture: {out}")
            print(json.dumps(fixture, indent=2, ensure_ascii=False))
        return

    # Resolve inputs
    if input_file:
        inputs = json.loads(input_file.read_text(encoding="utf-8"))
    else:
        # Look for test_input.json next to skill.yaml
        candidate = None
        if skill.source_file:
            candidate = Path(skill.source_file).parent / "test_input.json"
        if candidate and candidate.exists():
            inputs = json.loads(candidate.read_text(encoding="utf-8"))
            if not json_output:
                print(f"[test] Using fixture: {candidate}")
        else:
            # Auto-generate fixture
            inputs = generate_test_fixture(skill_doc)
            if not json_output:
                print("[test] No test_input.json found — using auto-generated fixture")

    engine = _build_engine(registry_root, runtime_root, host_root, local_skills_root)
    report = run_skill_test(engine=engine, skill_doc=skill_doc, inputs=inputs)

    if json_output:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        status_icon = "PASS" if report["ok"] else "FAIL"
        print(f"\n[test] {status_icon}: {skill_id}")
        print(f"  Status:       {report['status']}")
        print(f"  Duration:     {report['duration_ms']} ms")
        print(f"  Steps:        {report.get('steps_executed', '?')}")
        print(f"  Outputs:      {', '.join(report.get('output_keys', []))}")
        if report.get("missing_outputs"):
            print(f"  Missing:      {', '.join(report['missing_outputs'])}")
        if report.get("error"):
            print(f"  Error:        {report['error']}")

    if not report["ok"]:
        raise SystemExit(1)


# ---------------------------------------------------------------------------
# M8 — Check wiring
# ---------------------------------------------------------------------------


def _cmd_check_wiring(
    registry_root: Path,
    skill_id: str,
    json_output: bool,
) -> None:
    """Check type compatibility in skill dataflow."""
    from tooling.skill_authoring import check_wiring

    capability_loader = YamlCapabilityLoader(registry_root)
    capabilities = capability_loader.get_all_capabilities()

    # Load skill as raw dict
    skill_loader = YamlSkillLoader(registry_root)
    skill = skill_loader.get_skill(skill_id)
    skill_doc: dict = {"id": skill.id, "inputs": {}, "outputs": {}, "steps": []}
    for k, v in skill.inputs.items():
        skill_doc["inputs"][k] = {"type": getattr(v, "type", "string")}
    for k, v in skill.outputs.items():
        skill_doc["outputs"][k] = {"type": getattr(v, "type", "string")}

    if skill.source_file:
        raw = yaml.safe_load(Path(skill.source_file).read_text(encoding="utf-8"))
        skill_doc["steps"] = raw.get("steps", [])
    else:
        for s in skill.steps:
            skill_doc["steps"].append({"id": s.id, "uses": s.uses, "config": s.config})

    issues = check_wiring(skill_doc, capabilities)

    if json_output:
        print(
            json.dumps(
                {
                    "ok": len(issues) == 0,
                    "skill_id": skill_id,
                    "issues": issues,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        if not issues:
            print(f"[OK] {skill_id}: all step wiring looks consistent")
        else:
            for issue in issues:
                tag = issue.get("level", "warn").upper()
                print(f"[{tag}] step '{issue['step']}': {issue['message']}")
            print(f"\n{len(issues)} wiring issue(s) found in {skill_id}")


# ---------------------------------------------------------------------------
# M4 — Export / Import
# ---------------------------------------------------------------------------


def _cmd_export(
    registry_root: Path,
    runtime_root: Path,
    skill_id: str,
    out: Path | None,
    local_skills_root: Path | None = None,
) -> None:
    """Export a skill as a portable bundle."""
    from tooling.skill_authoring import export_skill_bundle

    skill_loader = YamlSkillLoader(registry_root)
    skill = skill_loader.get_skill(skill_id)

    if not skill.source_file:
        # Try finding in local skills
        local_root = local_skills_root or (runtime_root / "skills" / "local")
        if "." in skill_id:
            domain, slug = skill_id.split(".", 1)
            candidate = local_root / domain / slug / "skill.yaml"
            if candidate.exists():
                skill_file = candidate
            else:
                print(
                    f"[export] Cannot locate source file for '{skill_id}'",
                    file=sys.stderr,
                )
                raise SystemExit(1)
        else:
            print(
                f"[export] Cannot locate source file for '{skill_id}'", file=sys.stderr
            )
            raise SystemExit(1)
    else:
        skill_file = Path(skill.source_file)

    result = export_skill_bundle(skill_file, out)
    print(f"[export] Bundle created: {result}")
    print(
        f"[export] Share this file — recipient imports with: agent-skills import {result.name}"
    )


def _cmd_import(
    registry_root: Path,
    runtime_root: Path,
    source: str,
    json_output: bool,
    local_skills_root: Path | None = None,
) -> None:
    """Import a skill from a bundle or YAML file."""
    from tooling.skill_authoring import import_skill_bundle

    local_root = local_skills_root or (runtime_root / "skills" / "local")

    # Check if it's a tar.gz bundle or a plain YAML
    source_path = Path(source)
    if source_path.suffix == ".yaml" or source_path.suffix == ".yml":
        # Direct YAML import
        raw = yaml.safe_load(source_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or "id" not in raw:
            print("[import] Invalid skill YAML: missing 'id'", file=sys.stderr)
            raise SystemExit(1)
        sid = raw["id"]
        if "." not in sid:
            print(
                f"[import] Invalid skill id '{sid}' (expected domain.slug)",
                file=sys.stderr,
            )
            raise SystemExit(1)
        domain, slug = sid.split(".", 1)
        target_dir = local_root / domain / slug
        target_dir.mkdir(parents=True, exist_ok=True)
        import shutil

        shutil.copy2(str(source_path), str(target_dir / "skill.yaml"))
        report = {
            "ok": True,
            "skill_id": sid,
            "imported_to": str(target_dir),
            "files": ["skill.yaml"],
        }
    else:
        # Bundle import
        capability_loader = YamlCapabilityLoader(registry_root)
        capabilities = capability_loader.get_all_capabilities()
        report = import_skill_bundle(source, local_root, capabilities)

    if json_output:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        if report["ok"]:
            print(
                f"[import] Imported '{report['skill_id']}' to {report['imported_to']}"
            )
            print(f"[import] Files: {', '.join(report.get('files', []))}")
            if report.get("warnings"):
                for w in report["warnings"]:
                    print(f"[import] WARNING: {w}")
            print(f"[import] Next: agent-skills test {report['skill_id']}")
        else:
            print(
                f"[import] FAILED: {report.get('error', 'unknown error')}",
                file=sys.stderr,
            )
            raise SystemExit(1)


# ---------------------------------------------------------------------------
# M9 — Contribute one-liner
# ---------------------------------------------------------------------------


def _cmd_contribute(
    registry_root: Path,
    runtime_root: Path,
    host_root: Path,
    skill_id: str,
    channel: str,
    draft: bool,
    dry_run: bool,
    json_output: bool,
    local_skills_root: Path | None = None,
) -> None:
    """One-command contribution: similar-check → prepare → validate → PR."""
    from tooling.skill_authoring import find_similar_skills

    local_root = local_skills_root or (runtime_root / "skills" / "local")
    steps_done: list[str] = []

    # Step 1: Check for similar skills
    print("[contribute] Step 1/4: Checking for similar skills...")
    skills_root = registry_root / "skills"
    all_skills: dict[str, dict] = {}
    if skills_root.exists():
        for sf in skills_root.glob("**/skill.yaml"):
            try:
                raw = yaml.safe_load(sf.read_text(encoding="utf-8"))
                if isinstance(raw, dict) and raw.get("id"):
                    all_skills[raw["id"]] = raw
            except Exception:
                pass

    similar = find_similar_skills(skill_id, all_skills, top_n=3)
    if similar:
        print(f"[contribute] Found {len(similar)} similar skill(s):")
        for s in similar:
            print(f"  - {s['skill_id']} (similarity: {s['similarity']:.2f})")
        print("[contribute] Consider whether extending an existing skill is better.")
        print("[contribute] Continuing with contribution...\n")
    else:
        print("[contribute] No similar skills found — good to go.\n")
    steps_done.append("similar_check")

    # Step 2: Prepare package
    print("[contribute] Step 2/4: Preparing promotion package...")
    package_out_root = runtime_root / "artifacts" / "promotion_packages"
    package_out_root.mkdir(parents=True, exist_ok=True)

    try:
        result = prepare_promotion_package(
            local_skills_root=local_root,
            registry_root=registry_root,
            target_channel=channel,
            out_root=package_out_root,
            skill_id=skill_id,
        )
    except Exception as exc:
        print(f"[contribute] FAILED at prepare: {exc}", file=sys.stderr)
        raise SystemExit(1)

    print(f"[contribute] Package: {result.package_root}")
    steps_done.append("prepare")

    # Step 3: Validate
    print("\n[contribute] Step 3/4: Validating package...")
    validation = validate_promotion_package(
        package_root=result.package_root,
        registry_root=registry_root,
    )

    if validation.warnings:
        for w in validation.warnings:
            print(f"  [WARN] {w}")
    if validation.errors:
        print(
            f"\n[contribute] Validation FAILED with {len(validation.errors)} error(s):"
        )
        for e in validation.errors:
            print(f"  [ERROR] {e}")
        print(
            f"\n[contribute] Fix the issues in: {result.package_root / 'evidence' / 'admission_answers.yaml'}"
        )
        print(
            f"[contribute] Then re-run: agent-skills package-validate {result.package_root}"
        )
        raise SystemExit(1)
    print("[contribute] Validation passed.")
    steps_done.append("validate")

    # Step 4: PR
    if dry_run:
        print("\n[contribute] Step 4/4: (dry-run) Skipping PR creation.")
        print(f"[contribute] Package ready at: {result.package_root}")
        print(
            f"[contribute] To create PR: agent-skills package-pr {result.package_root}"
        )
        steps_done.append("dry_run")
    else:
        print("\n[contribute] Step 4/4: Creating PR...")
        _cmd_package_pr(
            registry_root,
            None,  # registry_repo_root
            result.package_root,
            "origin",
            "main",
            draft,
            False,
            json_output,
        )
        steps_done.append("pr")

    if json_output:
        print(
            json.dumps(
                {
                    "ok": True,
                    "skill_id": skill_id,
                    "channel": channel,
                    "steps": steps_done,
                    "package": str(result.package_root),
                    "similar_skills": similar,
                },
                indent=2,
                ensure_ascii=False,
            )
        )


# ---------------------------------------------------------------------------
# M11 — Rate a skill
# ---------------------------------------------------------------------------


def _cmd_rate(
    runtime_root: Path,
    skill_id: str,
    score: int,
    comment: str | None,
    json_output: bool,
) -> None:
    """Rate a skill locally."""
    from tooling.skill_authoring import rate_skill

    feedback_file = runtime_root / "artifacts" / "skill_feedback_local.json"
    result = rate_skill(skill_id, score, comment, feedback_file)

    if json_output:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        if result["ok"]:
            stars = "★" * score + "☆" * (5 - score)
            print(f"[rate] {skill_id}: {stars} ({score}/5)")
            print(
                f"  Average: {result['new_average']}/5 ({result['total_ratings']} ratings)"
            )
            if comment:
                print(f"  Comment: {comment}")
            print(f"  Saved to: {feedback_file}")
        else:
            print(f"[rate] ERROR: {result.get('error')}", file=sys.stderr)
            raise SystemExit(1)


# ---------------------------------------------------------------------------
# M12 — Report an issue
# ---------------------------------------------------------------------------


def _cmd_report(
    skill_id: str,
    issue_text: str,
    severity: str,
    open_browser: bool,
) -> None:
    """Generate a GitHub issue report for a skill."""
    from tooling.skill_authoring import generate_issue_report
    import urllib.parse

    report = generate_issue_report(skill_id, issue_text, severity)

    print(f"[report] Issue template for '{skill_id}':\n")
    print(f"Title: {report['title']}")
    print(f"Labels: {report['labels']}")
    print(f"\n{'─' * 60}")
    print(report["body"])
    print(f"{'─' * 60}")

    # Build GitHub URL
    repo_url = "https://github.com/gfernandf/agent-skills"
    params = urllib.parse.urlencode(
        {
            "title": report["title"],
            "body": report["body"],
            "labels": report["labels"],
        }
    )
    issue_url = f"{repo_url}/issues/new?{params}"

    print(f"\nCreate issue: {issue_url}")

    if open_browser:
        import webbrowser

        webbrowser.open(issue_url)
        print("[report] Opened in browser.")


# ---------------------------------------------------------------------------
# K4 — Skill Triggers
# ---------------------------------------------------------------------------


def _cmd_triggers(
    registry_root: Path,
    runtime_root: Path,
    host_root: Path,
    action: str,
    args,
    local_skills_root: Path | None = None,
) -> None:
    """Manage skill triggers: list, fire, status."""
    from runtime.triggers import TriggerRegistry, TriggerEvent, TriggerEngine

    reg = TriggerRegistry()
    # Load triggers from registry skills
    skills_root = registry_root / "skills"
    reg.load_from_skills_root(skills_root)
    # Also from local skills
    local_root = local_skills_root or (runtime_root / "skills" / "local")
    if local_root.exists():
        reg.load_from_skills_root(local_root)

    json_output = getattr(args, "json", False)

    if action == "list":
        type_filter = getattr(args, "type", None)
        triggers = reg.list_by_type(type_filter) if type_filter else reg.list_all()

        if json_output:
            print(
                json.dumps(
                    {
                        "triggers": [
                            {
                                "skill_id": t.skill_id,
                                "type": t.trigger_type,
                                "config": t.config,
                            }
                            for t in triggers
                        ],
                        "count": len(triggers),
                    },
                    indent=2,
                    ensure_ascii=False,
                )
            )
        else:
            if not triggers:
                print("[triggers] No triggers registered.")
                print(
                    "[triggers] Add a 'triggers:' section to your skill.yaml to define triggers."
                )
                return

            print(f"[triggers] {len(triggers)} trigger(s) registered:\n")
            for t in triggers:
                print(
                    f"  {t.skill_id:<40} type={t.trigger_type:<14} {_trigger_summary(t)}"
                )

    elif action == "fire":
        event_type = getattr(args, "event_type", "webhook")
        payload: dict = {}

        if getattr(args, "payload", None):
            try:
                payload = json.loads(args.payload)
            except json.JSONDecodeError:
                pass

        if event_type == "webhook":
            webhook_name = getattr(args, "webhook", None)
            if not webhook_name:
                print("[triggers] --webhook is required for webhook events")
                raise SystemExit(1)
            payload["webhook_name"] = webhook_name

        elif event_type == "event":
            source_skill = getattr(args, "source_skill", None)
            if not source_skill:
                print("[triggers] --source-skill is required for event type")
                raise SystemExit(1)
            payload["source_skill"] = source_skill
            payload["status"] = getattr(args, "status", "completed")

        elif event_type == "file_change":
            files_str = getattr(args, "files", None)
            if files_str:
                payload["changed_files"] = [f.strip() for f in files_str.split(",")]

        event = TriggerEvent(event_type=event_type, payload=payload)

        # Build engine for execution
        engine = _build_engine(
            registry_root, runtime_root, host_root, local_skills_root
        )

        def _execute_skill(skill_id: str, inputs: dict) -> dict:
            request = ExecutionRequest(
                skill_id=skill_id, inputs=inputs, channel="trigger"
            )
            result = engine.execute(request)
            return {
                "status": result.status,
                "outputs": dict(result.outputs) if result.outputs else {},
            }

        trigger_engine = TriggerEngine(registry=reg, execute_fn=_execute_skill)
        results = trigger_engine.fire(event)

        if json_output:
            print(
                json.dumps(
                    {
                        "event_type": event_type,
                        "payload": payload,
                        "results": results,
                        "matched": len(results),
                    },
                    indent=2,
                    ensure_ascii=False,
                )
            )
        else:
            if not results:
                print(f"[triggers] No triggers matched event: {event_type}")
            else:
                print(f"[triggers] Fired {len(results)} trigger(s):\n")
                for r in results:
                    status = r.get("status", "unknown")
                    icon = "✓" if status == "completed" else "✗"
                    print(f"  {icon} {r['skill_id']:<40} status={status}")

    elif action == "status":
        summary = reg.to_summary()
        if json_output:
            print(json.dumps(summary, indent=2, ensure_ascii=False))
        else:
            print("[triggers] Trigger Summary:")
            print(f"  Total: {summary['total_triggers']}")
            for ttype, count in summary.get("by_type", {}).items():
                print(f"  {ttype}: {count}")
            webhooks = summary.get("webhooks", {})
            if webhooks:
                print("\n  Webhooks:")
                for name, skills in webhooks.items():
                    print(f"    {name}: {', '.join(skills)}")
            chains = summary.get("event_chains", {})
            if chains:
                print("\n  Event chains:")
                for source, targets in chains.items():
                    print(f"    {source} → {', '.join(targets)}")


def _trigger_summary(t) -> str:
    """One-line summary of a trigger spec."""
    if t.trigger_type == "schedule":
        return f"expr={t.expression or 'default'}"
    elif t.trigger_type == "webhook":
        return f"name={t.webhook_name or '?'}"
    elif t.trigger_type == "event":
        return f"source={t.source_skill or '?'} on={t.on_status}"
    elif t.trigger_type == "file_change":
        pats = t.file_patterns
        return f"patterns={pats[:2]}{'...' if len(pats) > 2 else ''}"
    return ""


# ---------------------------------------------------------------------------
# K6 — Compose DSL
# ---------------------------------------------------------------------------


def _cmd_compose(
    registry_root: Path,
    runtime_root: Path,
    host_root: Path,
    source_path: str,
    out_path: Path | None,
    run: bool,
    extra_input: str | None,
    json_output: bool,
    local_skills_root: Path | None = None,
) -> None:
    """Compile a .compose file to skill.yaml, optionally execute."""
    from tooling.compose_dsl import parse_compose, compile_to_yaml, ComposeParseError

    source_file = Path(source_path)
    if not source_file.exists():
        print(f"[compose] ERROR: File not found: {source_file}")
        raise SystemExit(1)

    source_text = source_file.read_text(encoding="utf-8")

    try:
        spec = parse_compose(source_text, source_path=str(source_file))
    except ComposeParseError as exc:
        if json_output:
            print(
                json.dumps(
                    {"ok": False, "error": str(exc), "line": exc.line_num}, indent=2
                )
            )
        else:
            print(f"[compose] Parse error: {exc}")
        raise SystemExit(1)

    skill_doc = compile_to_yaml(spec)
    yaml_str = yaml.dump(
        skill_doc, default_flow_style=False, sort_keys=False, allow_unicode=True
    )

    # Write to file if requested
    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(yaml_str, encoding="utf-8")
        if not json_output:
            print(f"[compose] Compiled: {source_file} → {out_path}")
            print(f"[compose] Skill ID: {spec.skill_id}")
            print(f"[compose] Steps: {len(spec.steps)}")

    # Run mode: write to temp skill dir and execute
    if run:
        import tempfile

        # Write the compiled YAML to a temporary skill directory
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = (
                Path(tmpdir)
                / "skills"
                / "local"
                / "composed"
                / spec.skill_id.replace(".", "-")
            )
            skill_dir.mkdir(parents=True)
            (skill_dir / "skill.yaml").write_text(yaml_str, encoding="utf-8")

            # Resolve inputs
            inputs: dict = {}
            if extra_input:
                try:
                    inputs = json.loads(extra_input)
                except json.JSONDecodeError as exc:
                    print(f"[compose] Invalid --input JSON: {exc}")
                    raise SystemExit(1)
            else:
                # Auto-generate inputs from the skill document
                for name, field_info in skill_doc.get("inputs", {}).items():
                    ftype = field_info.get("type", "string")
                    if ftype == "string":
                        inputs[name] = f"test value for {name}"
                    elif ftype == "integer":
                        inputs[name] = 10
                    elif ftype == "number":
                        inputs[name] = 1.0
                    elif ftype == "boolean":
                        inputs[name] = True

            # Build engine with the temporary local skills directory
            engine = _build_engine(
                registry_root,
                runtime_root,
                host_root,
                local_skills_root=Path(tmpdir),
            )

            request = ExecutionRequest(
                skill_id=spec.skill_id,
                inputs=inputs,
                channel="compose",
            )
            result = engine.execute(request)

            output = {
                "ok": result.status == "completed",
                "skill_id": spec.skill_id,
                "status": result.status,
                "outputs": dict(result.outputs) if result.outputs else {},
            }

            if json_output:
                print(json.dumps(output, indent=2, ensure_ascii=False))
            else:
                if result.status == "completed":
                    print(f"[compose] ✓ Executed: {spec.skill_id}")
                    for k, v in (result.outputs or {}).items():
                        val_str = str(v)
                        if len(val_str) > 200:
                            val_str = val_str[:197] + "..."
                        print(f"  {k}: {val_str}")
                else:
                    error = getattr(result, "error", None) or result.status
                    print(f"[compose] ✗ Failed: {error}")
                    raise SystemExit(1)
        return

    # Default: print compiled YAML
    if not out_path:
        if json_output:
            print(
                json.dumps(
                    {"ok": True, "skill_id": spec.skill_id, "compiled": skill_doc},
                    indent=2,
                    ensure_ascii=False,
                )
            )
        else:
            print(f"# Compiled from: {source_file}")
            print(f"# Steps: {len(spec.steps)}, Outputs: {len(spec.outputs)}")
            print()
            print(yaml_str)


if __name__ == "__main__":
    main()

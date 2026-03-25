#!/usr/bin/env python3
"""Generate MCP binding YAML scaffolds for capabilities that lack MCP bindings.

Usage:
    python tooling/generate_mcp_bindings.py [--dry-run] [--limit N]

Reads the official_default_selection.yaml to discover all capabilities,
checks which already have MCP bindings, and generates scaffold YAML files
for the missing ones.

Each generated binding delegates to an in-process MCP server that must be
implemented in official_mcp_servers/.
"""
from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BINDINGS_DIR = ROOT / "bindings" / "official"
POLICIES_PATH = ROOT / "policies" / "official_default_selection.yaml"
MCP_SERVERS_DIR = ROOT / "official_mcp_servers"

# ── Priority capabilities for MCP binding rollout ────────────────
# Phase 1: 24 capabilities (from PRE_MCP_OPENAPI_READINESS.md)
PHASE_1_CAPABILITIES = [
    "text.content.generate",
    "text.content.rewrite",
    "text.content.classify",
    "text.content.extract",
    "text.sentiment.analyze",
    "text.language.detect",
    "text.language.translate",
    "data.json.parse",
    "data.record.transform",
    "data.record.deduplicate",
    "doc.content.chunk",
    "code.source.analyze",
    "code.source.format",
    "code.diff.extract",
    "code.snippet.execute",
    "fs.file.read",
    "fs.file.write",
    "fs.file.list",
    "analysis.problem.split",
    "analysis.risk.extract",
    "analysis.theme.cluster",
    "eval.option.score",
    "eval.option.analyze",
    "eval.output.score",
]


def _binding_template(capability_id: str) -> str:
    """Return YAML content for an MCP in-process binding scaffold."""
    domain = capability_id.split(".")[0]
    safe_id = capability_id.replace(".", "_")
    binding_id = f"mcp_{safe_id}_inprocess"
    service_id = f"{domain}_mcp_inprocess"
    return f"""# Auto-generated MCP binding scaffold for {capability_id}
# TODO: Implement tool in official_mcp_servers/{domain}_tools.py
id: {binding_id}
capability: {capability_id}
service: {service_id}
protocol: mcp
operation_id: {safe_id}
conformance_profile: baseline

request_template:
  # Map capability inputs to MCP tool arguments
  # TODO: Map each required input from the capability spec
  input_text: "{{{{ inputs.text }}}}"

response_template:
  # Map MCP tool results to capability outputs
  # TODO: Map each required output from the capability spec
  result: "{{{{ result }}}}"

metadata:
  phase: "mcp-rollout-phase-1"
  generated: true
  status: scaffold
"""


def _server_stub_template(domain: str, capabilities: list[str]) -> str:
    """Return Python content for an MCP server stub."""
    tool_functions = []
    for cap_id in capabilities:
        safe_id = cap_id.replace(".", "_")
        tool_functions.append(f'''
def {safe_id}(args: dict) -> dict:
    """MCP tool stub for {cap_id}. TODO: implement."""
    raise NotImplementedError("{cap_id} MCP tool not yet implemented")
''')

    return f'''"""MCP in-process server tools for {domain} domain.

Auto-generated scaffold. Implement each tool function to complete
the MCP binding rollout for this domain.
"""
from __future__ import annotations

TOOLS: dict[str, callable] = {{}}

{"".join(tool_functions)}

# Register all tools
{chr(10).join(f'TOOLS["{cap.replace(".", "_")}"] = {cap.replace(".", "_")}' for cap in capabilities)}
'''


def find_existing_mcp_bindings() -> set[str]:
    """Return capability IDs that already have MCP bindings."""
    existing: set[str] = set()
    if not BINDINGS_DIR.exists():
        return existing
    for cap_dir in BINDINGS_DIR.iterdir():
        if not cap_dir.is_dir():
            continue
        for f in cap_dir.iterdir():
            if "mcp" in f.name.lower() and f.suffix in (".yaml", ".yml"):
                # Extract capability from parent dir name
                existing.add(cap_dir.name.replace("-", "."))
    return existing


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate MCP binding scaffolds")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be generated")
    parser.add_argument("--limit", type=int, default=24, help="Max bindings to generate")
    args = parser.parse_args()

    existing = find_existing_mcp_bindings()
    to_generate = [c for c in PHASE_1_CAPABILITIES if c not in existing][:args.limit]

    if not to_generate:
        print("All Phase 1 capabilities already have MCP bindings.")
        return

    print(f"Generating MCP binding scaffolds for {len(to_generate)} capabilities:")

    # Group by domain for server stubs
    by_domain: dict[str, list[str]] = {}
    for cap_id in to_generate:
        domain = cap_id.split(".")[0]
        by_domain.setdefault(domain, []).append(cap_id)

    for cap_id in to_generate:
        cap_dir_name = cap_id.replace(".", "-")
        safe_id = cap_id.replace(".", "_")
        binding_dir = BINDINGS_DIR / cap_dir_name
        binding_file = binding_dir / f"mcp_{safe_id}_inprocess.yaml"

        if args.dry_run:
            print(f"  [DRY-RUN] Would create: {binding_file.relative_to(ROOT)}")
        else:
            binding_dir.mkdir(parents=True, exist_ok=True)
            binding_file.write_text(_binding_template(cap_id), encoding="utf-8")
            print(f"  Created: {binding_file.relative_to(ROOT)}")

    # Generate/update server stubs per domain
    for domain, caps in by_domain.items():
        stub_file = MCP_SERVERS_DIR / f"{domain}_tools.py"
        if stub_file.exists():
            if args.dry_run:
                print(f"  [DRY-RUN] Server stub exists, would skip: {stub_file.relative_to(ROOT)}")
            else:
                print(f"  Server stub exists, skipping: {stub_file.relative_to(ROOT)}")
        else:
            if args.dry_run:
                print(f"  [DRY-RUN] Would create server stub: {stub_file.relative_to(ROOT)}")
            else:
                stub_file.write_text(_server_stub_template(domain, caps), encoding="utf-8")
                print(f"  Created server stub: {stub_file.relative_to(ROOT)}")

    print(f"\nDone. {len(to_generate)} scaffolds {'would be ' if args.dry_run else ''}generated.")
    print("Next steps:")
    print("  1. Implement tool functions in official_mcp_servers/<domain>_tools.py")
    print("  2. Map inputs/outputs in each binding YAML")
    print("  3. Add entries to policies/official_default_selection.yaml")
    print("  4. Run: python validate_bindings.py")


if __name__ == "__main__":
    main()

# MCP Integration Slices

Date: 2026-03-12
Status: In progress
Scope: incremental MCP adoption without changing official defaults

## Purpose

This document tracks the incremental MCP rollout pattern used in this repository:

1. Add an official MCP service descriptor.
2. Add an official MCP binding for a capability.
3. Keep official default selection unchanged.
4. Activate MCP binding locally through `.agent-skills/active_bindings.json`.
5. Verify parity and metadata (`binding_id`, `service_id`) through tooling.

## Current Slices

1. text.content.summarize
- Service: `services/official/text_mcp_inprocess.yaml`
- Binding: `bindings/official/text.content.summarize/mcp_text_summarize_inprocess.yaml`
- Verification: `python tooling/verify_mcp_text_summarize.py`

2. data.schema.validate
- Service: `services/official/data_mcp_inprocess.yaml`
- Binding: `bindings/official/data.schema.validate/mcp_data_schema_validate_inprocess.yaml`
- Verification: `python tooling/verify_mcp_data_web_slices.py`

3. web.page.fetch
- Service: `services/official/web_mcp_inprocess.yaml`
- Binding: `bindings/official/web.page.fetch/mcp_web_fetch_inprocess.yaml`
- Verification: `python tooling/verify_mcp_data_web_slices.py`

## Runtime Wiring

- Default MCP client registry: `runtime/default_mcp_client_registry.py`
- Runtime assembly integration: `runtime/engine_factory.py`
- In-process MCP servers:
  - `official_mcp_servers/text_tools.py`
  - `official_mcp_servers/data_tools.py`
  - `official_mcp_servers/web_tools.py`

## Why Defaults Stay Unchanged

The official default map remains Python-backed during early rollout to avoid broad behavior changes.
MCP slices are validated via local activation and smoke tooling first.

## CI Coverage

The smoke workflow runs:

1. `python tooling/verify_mcp_text_summarize.py`
2. `python tooling/verify_mcp_data_web_slices.py`

This keeps MCP route regressions visible before promoting any capability to default MCP.

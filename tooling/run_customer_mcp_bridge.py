#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from customer_facing.mcp_tool_bridge import MCPToolBridge, run_stdio_bridge
from customer_facing.neutral_api import NeutralRuntimeAPI
from gateway.core import SkillGateway


def main() -> int:
    parser = argparse.ArgumentParser(description="Run MCP tool bridge over stdio.")
    parser.add_argument(
        "--runtime-root", type=Path, default=Path(__file__).resolve().parent.parent
    )
    parser.add_argument("--registry-root", type=Path, default=None)
    parser.add_argument("--host-root", type=Path, default=None)
    args = parser.parse_args()

    runtime_root = args.runtime_root
    registry_root = args.registry_root or (runtime_root.parent / "agent-skill-registry")
    host_root = args.host_root or runtime_root

    api = NeutralRuntimeAPI(
        registry_root=registry_root,
        runtime_root=runtime_root,
        host_root=host_root,
    )
    gateway = SkillGateway(
        registry_root=registry_root,
        runtime_root=runtime_root,
        host_root=host_root,
    )
    bridge = MCPToolBridge(api, gateway)
    return run_stdio_bridge(bridge)


if __name__ == "__main__":
    raise SystemExit(main())

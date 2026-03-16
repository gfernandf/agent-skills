#!/usr/bin/env python3

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from customer_facing.http_openapi_server import ServerConfig, run_server
from customer_facing.neutral_api import NeutralRuntimeAPI
from gateway.core import SkillGateway


def main() -> int:
    parser = argparse.ArgumentParser(description="Run customer-facing HTTP/OpenAPI server.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--api-key", default=None, help="Optional API key required via x-api-key header.")
    parser.add_argument("--rate-limit-requests", type=int, default=60)
    parser.add_argument("--rate-limit-window-seconds", type=int, default=60)
    parser.add_argument("--runtime-root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--registry-root", type=Path, default=None)
    parser.add_argument("--host-root", type=Path, default=None)
    parser.add_argument(
        "--openapi-spec",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "docs" / "specs" / "consumer_facing_v1_openapi.json",
    )
    args = parser.parse_args()

    runtime_root = args.runtime_root
    registry_root = args.registry_root or (runtime_root.parent / "agent-skill-registry")
    host_root = args.host_root or runtime_root
    api_key = args.api_key or os.getenv("CUSTOMER_API_KEY")

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

    run_server(
        api,
        gateway,
        config=ServerConfig(
            host=args.host,
            port=args.port,
            api_key=api_key,
            rate_limit_requests=args.rate_limit_requests,
            rate_limit_window_seconds=args.rate_limit_window_seconds,
        ),
        openapi_spec_path=args.openapi_spec,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

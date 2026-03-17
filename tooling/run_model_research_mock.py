#!/usr/bin/env python3
from __future__ import annotations

import time

from openapi_harness.mocks import start_mock_server


def main() -> int:
    server = start_mock_server({"type": "model_research", "host": "127.0.0.1", "port": 8765})
    print("model_research mock server running on 127.0.0.1:8765")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        server.stop()
        print("model_research mock server stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

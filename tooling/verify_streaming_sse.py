#!/usr/bin/env python3
"""Smoke test for SSE streaming endpoint.

Usage:
    python tooling/verify_streaming_sse.py [--host HOST] [--port PORT] [--skill SKILL_ID] [--api-key KEY]

Requires a running HTTP server.  Sends a request to /execute/stream and
validates that SSE events are received in the correct format.
"""

from __future__ import annotations

import argparse
import json
import sys
from urllib.request import Request, urlopen


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify SSE streaming endpoint")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--skill", default="text.content.generate")
    parser.add_argument("--api-key", default=None)
    args = parser.parse_args()

    url = f"http://{args.host}:{args.port}/v1/skills/{args.skill}/execute/stream"
    body = json.dumps({"inputs": {"text": "hello"}}).encode("utf-8")

    req = Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    if args.api_key:
        req.add_header("x-api-key", args.api_key)

    print(f"→ POST {url}")

    try:
        with urlopen(req, timeout=30) as resp:
            content_type = resp.headers.get("Content-Type", "")
            if "text/event-stream" not in content_type:
                print(f"✗ Expected Content-Type text/event-stream, got: {content_type}")
                sys.exit(1)

            print(f"  Content-Type: {content_type}")
            events = []

            for raw_line in resp:
                line = (
                    raw_line.decode("utf-8", errors="replace").rstrip("\n").rstrip("\r")
                )
                if line.startswith("event: "):
                    current_event = line[7:]
                elif line.startswith("data: "):
                    data = json.loads(line[6:])
                    events.append({"event": current_event, "data": data})
                    print(
                        f"  ← event: {current_event}  ({data.get('message', '')[:60]})"
                    )

            # Validation
            if not events:
                print("✗ No events received")
                sys.exit(1)

            last = events[-1]
            if last["event"] != "done":
                print(f"✗ Last event should be 'done', got '{last['event']}'")
                sys.exit(1)

            event_types = [e["event"] for e in events]
            print(f"\n✓ {len(events)} events received: {event_types}")
            print(f"✓ Final status: {last['data'].get('status', 'unknown')}")

    except Exception as e:
        print(f"✗ Connection error: {e}")
        print("  (Is the server running?)")
        sys.exit(1)


if __name__ == "__main__":
    main()

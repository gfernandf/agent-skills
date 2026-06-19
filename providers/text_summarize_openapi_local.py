#!/usr/bin/env python3
"""
Local OpenAPI provider for text.content.summarize (reasoning.content.summarize).

This is a Phase 1 pilot provider that demonstrates real service integration.
For production, replace this with an actual summarization backend (LLM API, etc.).

Usage:
  python providers/text_summarize_openapi_local.py --port 8781

Environment variables:
  PORT: Server port (default: 8781)
  HOST: Server host (default: 127.0.0.1)
"""

import sys
import argparse
from datetime import datetime
from typing import Optional

try:
    from fastapi import FastAPI, HTTPException, Request
    import uvicorn
except ImportError:
    print("ERROR: FastAPI and uvicorn required. Install with:")
    print("  pip install fastapi uvicorn")
    sys.exit(1)


app = FastAPI(
    title="Text Content Summarize Local API",
    version="1.0.0",
    description="Local provider for text.content.summarize pilot integration",
)


@app.get("/health")
async def health():
    """Health probe endpoint."""
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat() + "Z"}


@app.post("/summarize")
async def summarize(request: Request):
    """Summarize text content."""
    try:
        body = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {str(e)}")

    # Validate request
    if "text" not in body:
        raise HTTPException(status_code=400, detail="Missing required field: 'text'")

    text = body.get("text", "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Field 'text' cannot be empty")

    max_length = body.get("max_length", 150)
    if not isinstance(max_length, int) or max_length < 10 or max_length > 1000:
        raise HTTPException(
            status_code=400,
            detail="Field 'max_length' must be integer between 10 and 1000",
        )

    # Simulate summarization
    # In production, call actual LLM or summarization service
    try:
        summary = _synthesize_summary(text, max_length)
        status = "ok"
        error = None
    except Exception as e:
        summary = None
        status = "error"
        error = str(e)

    response = {
        "summary": summary if summary else text[:max_length],
        "status": status,
        "trace_ref": f"local-text-summarize-{datetime.utcnow().isoformat()}",
    }

    if error:
        response["error"] = error

    return response


def _synthesize_summary(text: str, max_length: int) -> Optional[str]:
    """
    Synthesize a summary of the text.

    This is a simple heuristic-based approach for Phase 1 pilot.
    Production implementations would use an LLM or proper summarization algorithm.
    """
    # Simple heuristic: extract first max_length characters, then truncate at word boundary
    if len(text) <= max_length:
        return text

    truncated = text[:max_length]
    # Find last word boundary
    last_space = truncated.rfind(" ")
    if last_space > 0:
        return truncated[:last_space] + "..."
    return truncated + "..."


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Local OpenAPI provider for text.content.summarize"
    )
    parser.add_argument("--host", default="127.0.0.1", help="Server host")
    parser.add_argument("--port", type=int, default=8781, help="Server port")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")

    args = parser.parse_args()

    print(f"Starting text.content.summarize local provider on {args.host}:{args.port}")
    print(f"Health endpoint: http://{args.host}:{args.port}/health")
    print(f"Summarize endpoint: http://{args.host}:{args.port}/summarize")

    uvicorn.run(
        app, host=args.host, port=args.port, reload=args.reload, log_level="info"
    )


if __name__ == "__main__":
    main()

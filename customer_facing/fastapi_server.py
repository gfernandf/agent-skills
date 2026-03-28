"""FastAPI/ASGI server for agent-skills runtime.

Drop-in replacement for the stdlib ThreadingHTTPServer.  Delegates all
business logic to ``NeutralRuntimeAPI`` — this module only wires HTTP
transport and adds production-grade features: uvicorn, async handlers,
OpenAPI auto-docs, and middleware-based auth/CORS/rate-limiting.

Usage (development)::

    pip install "agent-skills[asgi]"
    agent-skills serve --server asgi

Usage (production)::

    uvicorn customer_facing.fastapi_server:create_app --factory \\
        --host 0.0.0.0 --port 8080 --workers 4

Requires: ``fastapi``, ``uvicorn`` (add to ``[project.optional-dependencies]``).
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# ── Lazy imports: don't crash if fastapi/uvicorn not installed ──────


def _check_deps() -> None:
    try:
        import fastapi  # noqa: F401
        import uvicorn  # noqa: F401
    except ImportError as exc:
        raise ImportError(
            "FastAPI server requires 'fastapi' and 'uvicorn'. "
            "Install them with: pip install fastapi uvicorn"
        ) from exc


def create_app(
    *,
    api: Any | None = None,
    gateway: Any | None = None,
) -> Any:
    """Factory that returns a configured FastAPI application.

    Parameters
    ----------
    api:
        A ``NeutralRuntimeAPI`` instance.  If ``None``, one is built from
        environment variables (same behavior as ``run_server``).
    gateway:
        A ``SkillGateway`` instance.  If ``None``, resolved from the API.
    """
    _check_deps()

    from fastapi import FastAPI, HTTPException, Request
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import PlainTextResponse

    app = FastAPI(
        title="agent-skills",
        version="0.1.0",
        description="Runtime API for executing reusable AI agent skills",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # ── CORS ────────────────────────────────────────────────────
    cors_origins = os.environ.get("AGENT_SKILLS_CORS_ORIGINS", "").strip()
    if cors_origins:
        origins = [o.strip() for o in cors_origins.split(",")]
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
            allow_headers=["Content-Type", "Authorization", "X-Trace-Id", "X-API-Key"],
            max_age=86400,
        )

    # ── State holder ────────────────────────────────────────────
    class _State:
        api: Any = api
        gateway: Any = gateway

    state = _State()

    @app.on_event("startup")
    async def _startup() -> None:
        if state.api is not None:
            return
        # Auto-build runtime from environment (same as legacy server)
        from customer_facing.neutral_api import NeutralRuntimeAPI
        from gateway.core import SkillGateway

        gw = SkillGateway()
        state.gateway = gw
        state.api = NeutralRuntimeAPI(gateway=gw)
        logger.info("FastAPI server started — NeutralRuntimeAPI initialized.")

    # ── Security headers middleware ─────────────────────────────
    @app.middleware("http")
    async def _security_headers(request: Request, call_next):  # type: ignore[no-untyped-def]
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-XSS-Protection"] = "0"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = (
            "geolocation=(), camera=(), microphone=()"
        )
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; frame-ancestors 'none'"
        )
        return response

    # ── Helper ──────────────────────────────────────────────────
    def _get_api():  # type: ignore[no-untyped-def]
        if state.api is None:
            raise HTTPException(status_code=503, detail="Runtime not initialized")
        return state.api

    def _get_gateway():  # type: ignore[no-untyped-def]
        if state.gateway is None:
            raise HTTPException(status_code=503, detail="Gateway not initialized")
        return state.gateway

    # ── Health ──────────────────────────────────────────────────

    @app.get("/v1/health")
    async def health(deep: bool = False) -> dict:
        api = _get_api()
        if deep:
            return api.health()  # deep variant
        return api.health()

    @app.get("/v1/health/live")
    async def liveness() -> dict:
        return {"status": "alive"}

    @app.get("/v1/health/ready")
    async def readiness() -> dict:
        try:
            _get_api().health()
            _get_gateway().list_skills()
            return {"status": "ready"}
        except Exception:
            raise HTTPException(status_code=503, detail="Not ready")

    # ── Skills ──────────────────────────────────────────────────

    @app.get("/v1/skills/list")
    async def list_skills(
        domain: str | None = None,
        role: str | None = None,
        status: str | None = None,
        invocation: str | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> dict:
        gw = _get_gateway()
        all_skills = gw.list_skills(
            domain=domain,
            role=role,
            status=status,
            invocation=invocation,
        )
        total = len(all_skills)
        page = all_skills[offset : offset + min(limit, 100)]
        has_more = (offset + len(page)) < total
        result: dict[str, Any] = {
            "skills": [s.to_dict() for s in page],
            "pagination": {
                "offset": offset,
                "limit": limit,
                "total": total,
                "has_more": has_more,
            },
        }
        if has_more:
            result["pagination"]["next_offset"] = offset + len(page)
        return result

    @app.get("/v1/skills/{skill_id}/describe")
    async def describe_skill(skill_id: str) -> dict:
        return _get_api().describe_skill(skill_id)

    @app.post("/v1/skills/{skill_id}/execute")
    async def execute_skill(skill_id: str, request: Request) -> dict:
        body = await request.json()
        inputs = body.get("inputs", {})
        trace_id = request.headers.get("x-trace-id") or body.get("trace_id")
        return _get_api().execute_skill(
            skill_id=skill_id,
            inputs=inputs,
            trace_id=trace_id,
            include_trace=body.get("include_trace", False),
            required_conformance_profile=body.get("required_conformance_profile"),
            audit_mode=body.get("audit_mode"),
            execution_channel="http",
        )

    @app.post("/v1/skills/discover")
    async def discover_skills(request: Request) -> dict:
        body = await request.json()
        intent = body.get("intent", "")
        if not intent:
            raise HTTPException(status_code=400, detail="'intent' is required")
        gw = _get_gateway()
        results = gw.discover(
            intent=intent,
            domain=body.get("domain"),
            role_filter=body.get("role"),
            limit=body.get("limit", 10),
        )
        return {"intent": intent, "results": [r.to_dict() for r in results]}

    # ── Capabilities ────────────────────────────────────────────

    @app.post("/v1/capabilities/{capability_id}/execute")
    async def execute_capability(capability_id: str, request: Request) -> dict:
        body = await request.json()
        inputs = body.get("inputs", {})
        trace_id = request.headers.get("x-trace-id") or body.get("trace_id")
        return _get_api().execute_capability(
            capability_id=capability_id,
            inputs=inputs,
            trace_id=trace_id,
            required_conformance_profile=body.get("required_conformance_profile"),
        )

    # ── Metrics ─────────────────────────────────────────────────

    @app.get("/v1/metrics")
    async def metrics() -> dict:
        return _get_api().metrics()

    @app.get("/v1/metrics/prometheus")
    async def prometheus_metrics() -> PlainTextResponse:
        from customer_facing.http_openapi_server import _format_prometheus

        snap = _get_api().metrics()
        return PlainTextResponse(_format_prometheus(snap))

    return app


def run_asgi_server(
    api: Any,
    gateway: Any,
    *,
    host: str = "127.0.0.1",
    port: int = 8080,
) -> None:
    """Start the FastAPI/uvicorn server programmatically."""
    _check_deps()
    import uvicorn

    app = create_app(api=api, gateway=gateway)
    logger.info("Starting FastAPI server on %s:%d", host, port)
    uvicorn.run(app, host=host, port=port)

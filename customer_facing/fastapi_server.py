"""FastAPI/ASGI server for agent-skills runtime.

Drop-in replacement for the stdlib ThreadingHTTPServer.  Delegates all
business logic to ``NeutralRuntimeAPI`` — this module only wires HTTP
transport and adds production-grade features: uvicorn, async handlers,
OpenAPI auto-docs, and middleware-based auth/CORS/rate-limiting.

Usage (development)::

    pip install "orca-agent-skills[asgi]"
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
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

logger = logging.getLogger(__name__)


def _is_not_found_error(response: Any) -> bool:
    if not isinstance(response, dict):
        return False
    error = response.get("error")
    return isinstance(error, dict) and error.get("code") == "not_found"


def _unwrap_run_response(response: Any) -> Any:
    if not isinstance(response, dict):
        return response
    if response.get("ok") is True and isinstance(response.get("data"), dict):
        return response["data"]
    return response

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
        run_store: Any = None
        checkpoint_manager: Any = None
        async_pool: Any = None
        webhook_store: Any = None

    state = _State()

    @app.on_event("startup")
    async def _startup() -> None:
        if state.api is not None:
            # Ensure async infra is available when API is injected.
            if state.run_store is None:
                from runtime.run_store import RunStore

                state.run_store = RunStore(
                    max_runs=int(os.environ.get("AGENT_SKILLS_MAX_RUNS", "100"))
                )
            if state.checkpoint_manager is None:
                from runtime.checkpoint_manager import (
                    CheckpointManager,
                    FileCheckpointStoreBackend,
                )

                checkpoints_root = (
                    Path(os.environ.get("AGENT_SKILLS_RUNTIME_ROOT", Path.cwd()))
                    / "artifacts"
                    / "run_checkpoints"
                )
                state.checkpoint_manager = CheckpointManager(
                    FileCheckpointStoreBackend(checkpoints_root)
                )
            if state.async_pool is None:
                state.async_pool = ThreadPoolExecutor(
                    max_workers=int(os.environ.get("AGENT_SKILLS_ASYNC_WORKERS", "4"))
                )
            if state.webhook_store is None:
                from runtime.webhook import WebhookStore

                state.webhook_store = WebhookStore()
            return

        # Auto-build runtime from environment (same as legacy server)
        from customer_facing.neutral_api import NeutralRuntimeAPI
        from gateway.core import SkillGateway
        from runtime.checkpoint_manager import (
            CheckpointManager,
            FileCheckpointStoreBackend,
        )
        from runtime.run_store import RunStore
        from runtime.webhook import WebhookStore

        runtime_root = Path(
            os.environ.get("AGENT_SKILLS_RUNTIME_ROOT", Path.cwd())
        ).resolve()
        registry_root = Path(
            os.environ.get(
                "AGENT_SKILLS_REGISTRY_ROOT", runtime_root.parent / "agent-skill-registry"
            )
        ).resolve()
        host_root = Path(
            os.environ.get("AGENT_SKILLS_HOST_ROOT", runtime_root)
        ).resolve()

        gw = SkillGateway(
            registry_root=registry_root,
            runtime_root=runtime_root,
            host_root=host_root,
        )
        state.gateway = gw
        state.api = NeutralRuntimeAPI(
            registry_root=registry_root,
            runtime_root=runtime_root,
            host_root=host_root,
        )
        state.run_store = RunStore(
            max_runs=int(os.environ.get("AGENT_SKILLS_MAX_RUNS", "100"))
        )
        state.checkpoint_manager = CheckpointManager(
            FileCheckpointStoreBackend(runtime_root / "artifacts" / "run_checkpoints")
        )
        state.async_pool = ThreadPoolExecutor(
            max_workers=int(os.environ.get("AGENT_SKILLS_ASYNC_WORKERS", "4"))
        )
        state.webhook_store = WebhookStore()
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

    @app.post("/v1/skills/{skill_id}/execute/async", status_code=202)
    async def execute_skill_async(skill_id: str, request: Request) -> tuple[dict, int]:
        body = await request.json()
        inputs = body.get("inputs", {})
        trace_id = request.headers.get("x-trace-id") or body.get("trace_id")
        response = _get_api().execute_skill_async(
            skill_id=skill_id,
            inputs=inputs,
            trace_id=trace_id,
            required_conformance_profile=body.get("required_conformance_profile"),
            audit_mode=body.get("audit_mode"),
            execution_channel="http-async",
            run_store=state.run_store,
            checkpoint_manager=state.checkpoint_manager,
            async_pool=state.async_pool,
            webhook_store=state.webhook_store,
        )
        if "error" in response:
            raise HTTPException(status_code=500, detail=response["error"])
        return response

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

    # ── Async run status/list + aliases ─────────────────────────

    @app.get("/v1/runs")
    async def list_runs(
        limit: int = 100,
        offset: int = 0,
        status: str | None = None,
    ) -> dict:
        response = _get_api().list_runs(
            run_store=state.run_store,
            limit=limit,
            offset=offset,
            status=status,
        )
        if "error" in response:
            raise HTTPException(status_code=500, detail=response["error"])
        return response

    @app.get("/v1/runs/{run_id}")
    async def get_run(run_id: str) -> dict:
        response = _get_api().get_run(run_id, run_store=state.run_store)
        if _is_not_found_error(response):
            raise HTTPException(status_code=404, detail=response["error"])
        return _unwrap_run_response(response)

    @app.post("/v1/runs/{run_id}/cancel")
    async def cancel_run(run_id: str) -> dict:
        response = _get_api().cancel_run(run_id, run_store=state.run_store)
        if _is_not_found_error(response):
            raise HTTPException(status_code=404, detail=response["error"])
        return _unwrap_run_response(response)

    @app.get("/v1/runs/{run_id}/checkpoints")
    async def list_run_checkpoints(run_id: str) -> dict:
        response = _get_api().list_checkpoints(
            run_id,
            run_store=state.run_store,
            checkpoint_manager=state.checkpoint_manager,
        )
        if _is_not_found_error(response):
            raise HTTPException(status_code=404, detail=response["error"])
        return _unwrap_run_response(response)

    @app.post("/v1/runs/{run_id}/resume")
    async def resume_run(run_id: str, request: Request) -> dict:
        body = await request.json() if request.headers.get("content-length") else {}
        checkpoint_id = body.get("checkpoint_id") if isinstance(body, dict) else None
        response = _get_api().resume_run(
            run_id,
            run_store=state.run_store,
            checkpoint_manager=state.checkpoint_manager,
            checkpoint_id=checkpoint_id if isinstance(checkpoint_id, str) else None,
            async_pool=state.async_pool,
            webhook_store=state.webhook_store,
        )
        if _is_not_found_error(response):
            raise HTTPException(status_code=404, detail=response["error"])
        return _unwrap_run_response(response)

    @app.post("/v1/runs/{run_id}/approve")
    async def approve_run(run_id: str, request: Request) -> dict:
        body = await request.json() if request.headers.get("content-length") else {}
        response = _get_api().approve_run(
            run_id,
            approver=body.get("approver") if isinstance(body, dict) else None,
            notes=body.get("notes") if isinstance(body, dict) else None,
            run_store=state.run_store,
            checkpoint_manager=state.checkpoint_manager,
            async_pool=state.async_pool,
            webhook_store=state.webhook_store,
        )
        if _is_not_found_error(response):
            raise HTTPException(status_code=404, detail=response["error"])
        return _unwrap_run_response(response)

    @app.post("/v1/runs/{run_id}/deny")
    async def deny_run(run_id: str, request: Request) -> dict:
        body = await request.json() if request.headers.get("content-length") else {}
        response = _get_api().deny_run(
            run_id,
            approver=body.get("approver") if isinstance(body, dict) else None,
            notes=body.get("notes") if isinstance(body, dict) else None,
            run_store=state.run_store,
        )
        if _is_not_found_error(response):
            raise HTTPException(status_code=404, detail=response["error"])
        return _unwrap_run_response(response)

    @app.post("/v1/runs/{run_id}/replay")
    async def replay_run(run_id: str, request: Request) -> dict:
        body = await request.json() if request.headers.get("content-length") else {}
        checkpoint_id = body.get("checkpoint_id") if isinstance(body, dict) else None
        response = _get_api().replay_run(
            run_id,
            run_store=state.run_store,
            checkpoint_manager=state.checkpoint_manager,
            checkpoint_id=checkpoint_id if isinstance(checkpoint_id, str) else None,
            async_pool=state.async_pool,
            webhook_store=state.webhook_store,
        )
        if _is_not_found_error(response):
            raise HTTPException(status_code=404, detail=response["error"])
        return _unwrap_run_response(response)

    @app.post("/run_async", status_code=202)
    @app.post("/v1/run_async", status_code=202)
    async def run_async(request: Request) -> tuple[dict, int]:
        body = await request.json()
        skill_id = body.get("skill_id")
        if not isinstance(skill_id, str) or not skill_id:
            raise HTTPException(status_code=400, detail="'skill_id' is required")
        inputs = body.get("inputs", {})
        trace_id = request.headers.get("x-trace-id") or body.get("trace_id")
        response = _get_api().execute_skill_async(
            skill_id=skill_id,
            inputs=inputs if isinstance(inputs, dict) else {},
            trace_id=trace_id,
            required_conformance_profile=body.get("required_conformance_profile"),
            audit_mode=body.get("audit_mode"),
            execution_channel="http-async",
            run_store=state.run_store,
            checkpoint_manager=state.checkpoint_manager,
            async_pool=state.async_pool,
            webhook_store=state.webhook_store,
        )
        if "error" in response:
            raise HTTPException(status_code=500, detail=response["error"])
        return response

    @app.get("/run_status/{run_id}")
    @app.get("/v1/run_status/{run_id}")
    async def run_status(run_id: str) -> dict:
        response = _get_api().get_run(
            run_id,
            run_store=state.run_store,
            legacy_projection=True,
        )
        if _is_not_found_error(response):
            raise HTTPException(status_code=404, detail=response["error"])
        return _unwrap_run_response(response)

    @app.post("/run_cancel/{run_id}")
    @app.post("/v1/run_cancel/{run_id}")
    async def run_cancel(run_id: str) -> dict:
        response = _get_api().cancel_run(
            run_id,
            run_store=state.run_store,
            legacy_projection=True,
        )
        if _is_not_found_error(response):
            raise HTTPException(status_code=404, detail=response["error"])
        return _unwrap_run_response(response)

    # ── Webhooks (optional callbacks) ───────────────────────────

    @app.get("/v1/webhooks")
    async def list_webhooks() -> dict:
        if state.webhook_store is None:
            raise HTTPException(status_code=501, detail="Webhooks not enabled")
        return {"subscriptions": state.webhook_store.list_subscriptions()}

    @app.post("/v1/webhooks", status_code=201)
    async def create_webhook(request: Request) -> tuple[dict, int]:
        body = await request.json()
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="Request body must be a JSON object")
        url = body.get("url")
        if not isinstance(url, str) or not url:
            raise HTTPException(status_code=400, detail="webhooks require non-empty string field 'url'")
        events = body.get("events")
        if not isinstance(events, list) or not events:
            raise HTTPException(status_code=400, detail="webhooks require non-empty list field 'events'")

        from uuid import uuid4
        from runtime.webhook import WebhookSubscription

        if state.webhook_store is None:
            raise HTTPException(status_code=501, detail="Webhooks not enabled")

        sub_id = str(uuid4())
        sub = WebhookSubscription(
            id=sub_id,
            url=url,
            events=events,
            secret=body.get("secret", "") if isinstance(body.get("secret", ""), str) else "",
            active=True,
            created_at="",
        )
        try:
            state.webhook_store.register(sub)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return {"id": sub_id, "url": url, "events": events}

    @app.delete("/v1/webhooks/{sub_id}")
    async def delete_webhook(sub_id: str) -> dict:
        if state.webhook_store is None:
            raise HTTPException(status_code=501, detail="Webhooks not enabled")
        deleted = state.webhook_store.unregister(sub_id)
        if not deleted:
            raise HTTPException(status_code=404, detail=f"Webhook '{sub_id}' not found")
        return {"status": "deleted", "id": sub_id}

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

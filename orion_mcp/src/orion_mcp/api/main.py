from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from orion_mcp.api.routes.chat import _hints_from_chat_request, router as chat_router
from orion_mcp.api.schemas import ChatRequest, ChatResponse
from orion_mcp.core.config.settings import get_settings
from orion_mcp.core.orchestrator.orchestrator import Orchestrator
from orion_mcp.core.tools.registry import ToolRegistry
from orion_mcp.infra.cache.tool_cache import MemoryToolCache, RedisToolCache
from orion_mcp.infra.db.migrate import run_migrations
from orion_mcp.infra.db.pool import create_pool
from orion_mcp.infra.db.state_repository import MemoryStateRepository, PostgresStateRepository
from orion_mcp.infra.observability.tracing import setup_tracing

_logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    if os.getenv("ORION_OTEL_CONSOLE", "").lower() in ("1", "true", "yes"):
        setup_tracing()

    pool = await create_pool(settings)
    if pool is not None:
        await run_migrations(settings)
        repo: MemoryStateRepository | PostgresStateRepository = PostgresStateRepository(pool)
    else:
        db = (settings.database_url or "").strip()
        if settings.db_required or (settings.is_production and db):
            raise RuntimeError("Database obrigatório indisponível")
        repo = MemoryStateRepository()

    cache = MemoryToolCache()
    redis_client = None
    if settings.redis_url:
        try:
            import redis.asyncio as redis

            redis_client = redis.from_url(settings.redis_url, decode_responses=True)
            await redis_client.ping()
            cache = RedisToolCache(redis_client)
        except Exception:
            _logger.warning("Redis indisponível; cache em memória.", exc_info=True)
            redis_client = None
            cache = MemoryToolCache()

    tools = ToolRegistry(settings, cache=cache)
    app.state.settings = settings
    app.state.pool = pool
    app.state.redis = redis_client
    app.state.orchestrator = Orchestrator.build(settings, repo, tools, pool)

    yield

    if redis_client is not None:
        await redis_client.aclose()
    if pool is not None:
        await pool.close()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Orion MCP", version="0.1.0", lifespan=lifespan)
    app.include_router(chat_router)

    if settings.api_enable_legacy_chat_alias:
        from collections.abc import AsyncIterator

        from fastapi.responses import StreamingResponse

        @app.post("/api/chat", response_model=ChatResponse, tags=["chat"])
        async def chat_alias(body: ChatRequest, request: Request) -> ChatResponse:
            orch: Orchestrator = request.app.state.orchestrator
            from orion_mcp.core.strategy import Strategy

            strat = Strategy.fast if body.strategy == "fast" else Strategy.deep
            sid = body.resolved_session_id()
            hints = _hints_from_chat_request(body)
            result = await orch.handle_chat(
                session_id=sid,
                user_input=body.message,
                strategy=strat,
                hints=hints,
            )
            return ChatResponse(session_id=sid, payload=result.payload, metrics=result.metrics)

        @app.post(
            "/api/chat/stream",
            response_model=None,
            response_class=StreamingResponse,
            responses={
                200: {
                    "description": "Fluxo SSE (`text/event-stream`).",
                    "content": {"text/event-stream": {"schema": {"type": "string", "format": "binary"}}},
                }
            },
            tags=["chat"],
        )
        async def chat_stream_alias(body: ChatRequest, request: Request):
            orch = request.app.state.orchestrator
            from orion_mcp.core.strategy import Strategy

            strat = Strategy.fast if body.strategy == "fast" else Strategy.deep
            sid = body.resolved_session_id()

            async def gen() -> AsyncIterator[str]:
                hints = _hints_from_chat_request(body)
                async for line in orch.handle_chat_stream(
                    session_id=sid,
                    user_input=body.message,
                    strategy=strat,
                    hints=hints,
                ):
                    yield line

            return StreamingResponse(gen(), media_type="text/event-stream")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "orion-mcp"}

    @app.get("/metrics")
    def metrics() -> PlainTextResponse:
        data = generate_latest()
        return PlainTextResponse(content=data.decode("utf-8"), media_type=CONTENT_TYPE_LATEST)

    return app


app = create_app()

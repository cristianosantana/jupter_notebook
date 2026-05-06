from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.responses import Response

from orion_mcp_v2.cache.redis_memory import MemoryRedisStore
from orion_mcp_v2.config.settings import Settings, get_settings
from orion_mcp_v2.core.orchestrator.orchestrator import OrionOrchestratorV2
from orion_mcp_v2.db.mysql.mysql_pool import close_mysql_pool, create_mysql_pool
from orion_mcp_v2.db.mysql.query_executor import AnalyticsQueryExecutor
from orion_mcp_v2.db.postgres.pool import close_pool, create_pool
from orion_mcp_v2.llm_provider.openai_provider import OpenAIChatService
from orion_mcp_v2.observability.health import router as health_router
from orion_mcp_v2.observability.tracing import setup_tracing
from orion_mcp_v2.route.chat import router as chat_router
from orion_mcp_v2.route.chat_stream import router as chat_stream_router
from orion_mcp_v2.skill.loader import load_all_skills
from orion_mcp_v2.state.repository import StateRepository

logging.basicConfig(level=logging.INFO)
_logger = logging.getLogger(__name__)


def build_app(settings: Settings | None = None) -> FastAPI:
    cfg = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if cfg.otel_enabled:
            setup_tracing(service_name=cfg.app_name)
        app.state.settings = cfg
        app.state.pg_pool = await create_pool(cfg)
        app.state.mysql_pool = await create_mysql_pool(cfg.mysql_url)
        app.state.redis_memory_raw = None
        app.state.redis_limiter = None
        if cfg.redis_url:
            try:
                import redis.asyncio as redis_async

                app.state.redis_memory_raw = redis_async.from_url(cfg.redis_url, decode_responses=True)
                await app.state.redis_memory_raw.ping()
                app.state.redis_limiter = app.state.redis_memory_raw
            except Exception:
                _logger.warning("redis_unavailable", exc_info=True)
                app.state.redis_memory_raw = None
                app.state.redis_limiter = None

        mem = MemoryRedisStore(app.state.redis_memory_raw, ttl_seconds=cfg.memory_curta_ttl_seconds)
        skills = load_all_skills()
        llm = OpenAIChatService(cfg)
        mysql_exec = AnalyticsQueryExecutor(app.state.mysql_pool)
        repo = StateRepository(app.state.pg_pool)
        app.state.orchestrator = OrionOrchestratorV2(cfg, repo, mysql_exec, mem, skills, llm)

        yield

        if app.state.redis_memory_raw is not None:
            await app.state.redis_memory_raw.aclose()
        await close_mysql_pool(app.state.mysql_pool)
        await close_pool(app.state.pg_pool)

    app = FastAPI(title=cfg.app_name, lifespan=lifespan)
    app.include_router(health_router)
    app.include_router(chat_router)
    app.include_router(chat_stream_router)

    @app.get("/metrics")
    async def metrics():
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return app


app = build_app()

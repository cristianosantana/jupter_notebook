from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import grpc.aio
import uvicorn

from orion_mcp.mcp_adapter.grpc_gen import orion_mcp_tools_pb2_grpc as pb2_grpc
from orion_mcp.mcp_adapter.server.config import McpGrpcServerSettings
from orion_mcp.mcp_adapter.server.grpc_servicer import AnalyticsServiceServicer, McpServerRuntime
from orion_mcp.mcp_adapter.server.mysql_pool import close_mysql_pool, create_mysql_pool
from orion_mcp.mcp_adapter.server.query_executor import QueryExecutor

_logger = logging.getLogger(__name__)


async def start_grpc_server_pair(
    settings: McpGrpcServerSettings,
) -> tuple[grpc.aio.Server, Any]:
    pool = await create_mysql_pool(
        settings.mcp_mysql_url,
        minsize=settings.mcp_mysql_pool_minsize,
        maxsize=settings.mcp_mysql_pool_maxsize,
    )
    redis_client: Any = None
    url = settings.effective_redis_url()
    if url:
        import redis.asyncio as redis

        redis_client = redis.from_url(url, decode_responses=False)
        _logger.info("mcp_redis_l2_connected")

    sem = asyncio.Semaphore(settings.mcp_query_concurrency)
    executor = QueryExecutor(pool, compact_sample_rows=settings.tool_llm_preview_rows)
    runtime = McpServerRuntime(
        mysql_pool=pool,
        redis=redis_client,
        l2_ttl_seconds=settings.mcp_l2_cache_ttl_seconds,
        semaphore=sem,
        query_executor=executor,
    )
    server = grpc.aio.server(
        migration_thread_pool=ThreadPoolExecutor(max_workers=8),
        options=[
            ("grpc.max_send_message_length", 32 * 1024 * 1024),
            ("grpc.max_receive_message_length", 32 * 1024 * 1024),
        ],
    )
    pb2_grpc.add_AnalyticsServiceV1Servicer_to_server(AnalyticsServiceServicer(runtime), server)
    listen = f"{settings.mcp_server_grpc_host}:{settings.mcp_server_grpc_port}"
    server.add_insecure_port(listen)
    await server.start()
    _logger.info("mcp_grpc_serving", extra={"addr": listen})

    async def _shutdown() -> None:
        await server.stop(grace=5)
        await close_mysql_pool(pool)
        if redis_client is not None:
            await redis_client.aclose()

    return server, _shutdown


async def _async_main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    settings = McpGrpcServerSettings()
    server, shutdown_cb = await start_grpc_server_pair(settings)

    gateway_task: asyncio.Task[Any] | None = None
    if settings.mcp_http_gateway_enabled:
        from orion_mcp.mcp_adapter.gateway.app import create_gateway_app

        app = create_gateway_app(
            grpc_target=f"127.0.0.1:{settings.mcp_server_grpc_port}",
        )
        config = uvicorn.Config(
            app,
            host=settings.mcp_http_gateway_host,
            port=settings.mcp_http_gateway_port,
            log_level="info",
        )
        uv_server = uvicorn.Server(config)
        gateway_task = asyncio.create_task(uv_server.serve())
        _logger.info(
            "mcp_http_gateway_started",
            extra={"host": settings.mcp_http_gateway_host, "port": settings.mcp_http_gateway_port},
        )

    try:
        await server.wait_for_termination()
    finally:
        if gateway_task is not None:
            gateway_task.cancel()
            try:
                await gateway_task
            except asyncio.CancelledError:
                pass
        await shutdown_cb()


def main() -> None:
    asyncio.run(_async_main())

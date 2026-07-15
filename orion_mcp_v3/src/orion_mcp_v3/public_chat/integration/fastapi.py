"""Integração FastAPI — único ponto de cola Orion → public_chat."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI

from orion_mcp_v3.protocols.llm import LLMProvider
from orion_mcp_v3.public_chat.api.routes import create_public_ask_router
from orion_mcp_v3.public_chat.application.consulta_turn_runner import ConsultaTurnRunner
from orion_mcp_v3.public_chat.application.factory import build_public_chat_runner
from orion_mcp_v3.public_chat.config.settings import PublicChatSettings, load_settings
from orion_mcp_v3.public_chat.infrastructure.database import create_database_pool
from orion_mcp_v3.public_chat.infrastructure.pipeline_trace import (
    configure_public_chat_file_logging,
    current_log_file_path,
    log_public_chat_event,
    shutdown_public_chat_file_logging,
)

_LOG = logging.getLogger("orion.public_chat.integration")


def mount_public_chat(
    app: FastAPI,
    *,
    shared_state: dict[str, Any],
    llm_provider: LLMProvider | None = None,
) -> None:
    """Monta rotas do Chat Público; runner inicializado no startup ou no primeiro pedido."""
    settings = load_settings()
    shared_state["public_chat_settings"] = settings
    shared_state["public_chat_llm_provider"] = llm_provider

    log_path = configure_public_chat_file_logging(settings)
    if log_path is not None:
        _LOG.info("Public chat pipeline JSONL: %s", log_path)

    # log_public_chat_event(
    #     etapa="integration.mount",
    #     fase="post",
    #     dados={
    #         "enabled": settings.enabled,
    #         "runtime_ready": settings.runtime_ready,
    #         "pipeline_log_file": str(current_log_file_path()) if log_path else None,
    #     },
    # )

    async def _ensure_runner() -> ConsultaTurnRunner | None:
        cached = shared_state.get("public_chat_runner")
        if cached is not None:
            return cached

        cfg: PublicChatSettings = shared_state.get("public_chat_settings") or load_settings()
        if not cfg.enabled or not cfg.runtime_ready:
            return None

        pool = shared_state.get("postgres_pool")
        if pool is None:
            pool = await create_database_pool(cfg, required=True)
            shared_state["public_chat_owned_pool"] = pool

        provider = shared_state.get("public_chat_llm_provider")
        runner = build_public_chat_runner(pool=pool, settings=cfg, llm_provider=provider)
        shared_state["public_chat_runner"] = runner
        # log_public_chat_event(
        #     etapa="integration.runner_init",
        #     fase="post",
        #     dados={"pool_shared": shared_state.get("postgres_pool") is pool},
        # )
        _LOG.info("Public chat runner initialized")
        return runner

    async def _public_chat_startup() -> None:
        cfg: PublicChatSettings = shared_state.get("public_chat_settings") or load_settings()
        if not cfg.enabled:
            return
        try:
            await _ensure_runner()
        except Exception:
            _LOG.exception("Failed to initialize public chat runner on startup")

    def _public_chat_shutdown() -> None:
        shutdown_public_chat_file_logging()

    shared_state["public_chat_startup"] = _public_chat_startup
    shared_state["public_chat_shutdown"] = _public_chat_shutdown

    app.include_router(
        create_public_ask_router(_ensure_runner),
        prefix="/api/v1",
    )

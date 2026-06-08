"""
FastAPI application (Fase 6.1 + 7.1) — ponto de entrada da API de produto.

Usa :func:`~orion_mcp_v3.config.settings.get_settings` para configuração central.

Uso (na raiz do repo, com o venv ativo):
    pip install -e .
    uvicorn orion_mcp_v3.api.main:app --reload

Sem instalar o pacote (PYTHONPATH via uvicorn):
    uvicorn --app-dir src orion_mcp_v3.api.main:app --reload
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from orion_mcp_v3.api.email import EmailSender
from orion_mcp_v3.api.models import HealthResponse
from orion_mcp_v3.api.routes.chat import create_chat_router
from orion_mcp_v3.broker.executor import AnalyticsExecutor
from orion_mcp_v3.broker.sql_compiler import SqlAllowlist
from orion_mcp_v3.config.allowlists import ANALYTICS_ALLOWLIST
from orion_mcp_v3.config.settings import OrionSettings, get_settings
from orion_mcp_v3.protocols.llm import LLMProvider, NullLLMProvider
from orion_mcp_v3.runtime.attention_policy import AttentionPolicy
from orion_mcp_v3.runtime.analytics_pipeline_trace import (
    configure_pipeline_file_logging,
    shutdown_pipeline_file_logging,
)
from orion_mcp_v3.runtime.narrator import CognitiveNarrator
from orion_mcp_v3.runtime.session_manager import SessionManager

_LOG = logging.getLogger("orion.api.main")


def _configure_logging(s: OrionSettings) -> None:
    level = getattr(logging, s.log_level.upper(), logging.INFO)
    if s.log_format == "json":
        fmt = '{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","message":"%(message)s"}'
    else:
        fmt = "%(asctime)s %(levelname)-8s %(name)s %(message)s"
    logging.basicConfig(level=level, format=fmt, force=True)


def _resolve_policy(name: str) -> AttentionPolicy:
    try:
        return AttentionPolicy(name.strip().lower())
    except ValueError:
        return AttentionPolicy.BALANCED


def _build_provider(settings: OrionSettings) -> LLMProvider:
    if settings.llm_enabled:
        try:
            from orion_mcp_v3.providers.openai_provider import OpenAIProvider
            return OpenAIProvider(
                api_key=settings.llm_api_key,
                model=settings.llm_model,
                max_tokens=settings.llm_max_tokens,
                base_url=settings.llm_base_url or None,
            )
        except ImportError:
            pass
    return NullLLMProvider()


def _build_lifespan(
    s: OrionSettings,
    state: dict[str, Any],
):
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if s.mysql_enabled and state.get("executor") is None:
            try:
                from orion_mcp_v3.connection_hub.pools import create_mysql_pool, close_mysql_pool
                from orion_mcp_v3.connection_hub.mysql_backend import MysqlDatastoreClient

                pool = await create_mysql_pool(
                    s.mysql_url,
                    minsize=s.mysql_pool_min,
                    maxsize=s.mysql_pool_max,
                )
                if pool is not None:
                    client = MysqlDatastoreClient(pool)
                    executor = AnalyticsExecutor(
                        client,
                        ANALYTICS_ALLOWLIST,
                        default_limit=s.default_limit,
                    )
                    state["pool"] = pool
                    state["executor"] = executor
                    state["allowlist"] = ANALYTICS_ALLOWLIST
                    _LOG.info("MySQL analytics executor initialised (pool=%s)", s.mysql_url.split("@")[-1])
            except Exception:
                _LOG.exception("Failed to create MySQL pool — analytics disabled")

        if s.postgres_enabled and state.get("conversation_repository") is None:
            try:
                from orion_mcp_v3.connection_hub.pools import create_postgres_pool
                from orion_mcp_v3.memory.repositories.postgres_conversation_state import (
                    PostgresConversationStateRepository,
                )

                pg_pool = await create_postgres_pool(
                    s.postgres_url,
                    min_size=s.postgres_pool_min,
                    max_size=s.postgres_pool_max,
                )
                if pg_pool is not None:
                    state["postgres_pool"] = pg_pool
                    state["conversation_repository"] = PostgresConversationStateRepository(pg_pool)
                    _LOG.info("PostgreSQL conversation store enabled (%s)", s.postgres_url.split("@")[-1])
                    if s.embedding_active:
                        try:
                            from orion_mcp_v3.memory.chat_turn_embedding_store import ChatTurnEmbeddingStore
                            from orion_mcp_v3.providers.openai_embedding import OpenAIEmbeddingService

                            embed_svc = OpenAIEmbeddingService(
                                api_key=s.llm_api_key,
                                model=s.embedding_model,
                                dimensions=s.embedding_dimensions,
                                base_url=s.llm_base_url or None,
                            )
                            state["chat_turn_embedding_store"] = ChatTurnEmbeddingStore(pg_pool, embed_svc)
                            _LOG.info(
                                "Memory Augmentation enabled (mode=%s, model=%s, dims=%s)",
                                s.effective_embedding_mode,
                                s.embedding_model,
                                s.embedding_dimensions,
                            )
                        except Exception:
                            _LOG.exception(
                                "Embeddings desactivados — falha ao iniciar ChatTurnEmbeddingStore"
                            )
            except Exception:
                _LOG.exception("Failed to create PostgreSQL pool — conversation persistence in-memory only")

        yield

        shutdown_pipeline_file_logging()

        state.pop("conversation_repository", None)
        state.pop("chat_turn_embedding_store", None)
        pg_pool = state.pop("postgres_pool", None)
        if pg_pool is not None:
            from orion_mcp_v3.connection_hub.pools import close_postgres_pool

            await close_postgres_pool(pg_pool)
            _LOG.info("PostgreSQL pool closed")

        pool = state.get("pool")
        if pool is not None:
            from orion_mcp_v3.connection_hub.pools import close_mysql_pool
            await close_mysql_pool(pool)
            _LOG.info("MySQL pool closed")

    return lifespan


def create_app(
    *,
    llm_provider: LLMProvider | None = None,
    session_manager: SessionManager | None = None,
    settings: OrionSettings | None = None,
    analytics_executor: AnalyticsExecutor | None = None,
    analytics_allowlist: SqlAllowlist | None = None,
    email_sender: EmailSender | None = None,
) -> FastAPI:
    """Factory da aplicação FastAPI com dependências injectáveis."""
    s = settings or get_settings()
    _configure_logging(s)
    jsonl_path = configure_pipeline_file_logging(s)
    if jsonl_path is not None:
        _LOG.info("Analytics pipeline JSONL: %s", jsonl_path)

    state: dict[str, Any] = {}
    if analytics_executor is not None:
        state["executor"] = analytics_executor
        state["allowlist"] = analytics_allowlist or ANALYTICS_ALLOWLIST

    app = FastAPI(
        title="Orion Cognitive Copilot",
        version="0.8.0",
        description="Runtime cognitivo orientado a contexto — API de produto.",
        debug=s.api_debug,
        lifespan=_build_lifespan(s, state),
    )

    if s.api_cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=s.cors_origins_list,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    provider = llm_provider or _build_provider(s)
    default_policy = _resolve_policy(s.default_policy)
    if session_manager is None:
        sm = SessionManager(
            default_token_budget=s.max_tokens,
            default_policy=default_policy,
            memory_window=s.memory_window,
            session_list_max_messages=s.session_list_max_messages,
            shared_conversation_repository_slot=state,
        )
    else:
        sm = session_manager
    narrator = CognitiveNarrator(provider)
    resolved_email_sender = email_sender
    if resolved_email_sender is None and s.email_configured:
        resolved_email_sender = EmailSender.from_settings(s, llm_provider=provider)
        _LOG.info(
            "Email sender enabled (driver=%s, host=%s:%s, start_tls=%s, from=%s)",
            s.email_driver_name,
            s.effective_email_host,
            s.effective_email_port,
            s.email_start_tls,
            s.email_from_address,
        )
    elif resolved_email_sender is None:
        _LOG.info(
            "Email sender disabled (enabled=%s, host_present=%s, from_present=%s)",
            s.email_enabled,
            bool(s.effective_email_host.strip()),
            bool(s.email_from_address.strip()),
        )
    else:
        _LOG.info("Email sender injected (%s)", type(resolved_email_sender).__name__)

    chat_router = create_chat_router(
        session_manager=sm,
        llm_provider=provider,
        narrator=narrator,
        analytics_executor=state.get("executor"),
        analytics_allowlist=state.get("allowlist"),
        analytics_state=state,
        email_sender=resolved_email_sender,
    )
    app.include_router(chat_router)

    @app.get("/health", response_model=HealthResponse, tags=["infra"])
    async def health() -> HealthResponse:
        return HealthResponse()

    return app


app = create_app()

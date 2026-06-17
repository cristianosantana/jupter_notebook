"""Fábrica de componentes do Chat Público."""

from __future__ import annotations

import asyncpg

from orion_mcp_v3.protocols.llm import LLMProvider, NullLLMProvider
from orion_mcp_v3.public_chat.application.consulta_turn_runner import ConsultaTurnRunner
from orion_mcp_v3.public_chat.config.settings import PublicChatSettings, load_settings
from orion_mcp_v3.public_chat.infrastructure.database import build_response_store
from orion_mcp_v3.public_chat.infrastructure.embedding import OpenAIPublicEmbeddingService
from orion_mcp_v3.public_chat.infrastructure.intent_interpreter import PublicIntentInterpreter
from orion_mcp_v3.public_chat.infrastructure.llm import OpenAIPublicLLMProvider
from orion_mcp_v3.public_chat.infrastructure.narrator import PublicNarrator
from orion_mcp_v3.public_chat.infrastructure.remissive_reader import PublicRemissiveReader
from orion_mcp_v3.public_chat.infrastructure.remissive_retriever import RemissiveRetriever


def resolve_llm_provider(
    settings: PublicChatSettings,
    injected: LLMProvider | None = None,
) -> LLMProvider:
    if injected is not None and not isinstance(injected, NullLLMProvider):
        return injected
    if settings.llm_enabled:
        return OpenAIPublicLLMProvider(
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            max_tokens=settings.narrator_max_tokens,
            base_url=settings.llm_base_url,
        )
    return injected or NullLLMProvider()


def build_public_chat_runner(
    *,
    pool: asyncpg.Pool,
    llm_provider: LLMProvider | None = None,
    settings: PublicChatSettings | None = None,
    embedding_service: OpenAIPublicEmbeddingService | None = None,
) -> ConsultaTurnRunner:
    cfg = settings or load_settings()
    provider = resolve_llm_provider(cfg, llm_provider)
    embed = embedding_service or OpenAIPublicEmbeddingService(
        api_key=cfg.effective_embedding_api_key,
        model=cfg.embedding_model,
        dimensions=cfg.embedding_dimensions,
        base_url=cfg.llm_base_url,
    )
    store = build_response_store(pool)
    reader = PublicRemissiveReader(
        pool,
        embed,
        probes=cfg.ivfflat_probes,
        limit=cfg.retrieval_limit,
    )
    retriever = RemissiveRetriever(reader)
    intent = PublicIntentInterpreter(
        provider,
        max_tokens=cfg.intent_max_tokens,
        min_confidence=cfg.intent_min_confidence,
    )
    narrator = PublicNarrator(provider, max_tokens=cfg.narrator_max_tokens)
    return ConsultaTurnRunner(
        settings=cfg,
        store=store,
        intent_interpreter=intent,
        retriever=retriever,
        narrator=narrator,
    )


def build_runner_miss_only(
    *,
    pool: asyncpg.Pool,
    llm_provider: LLMProvider,
    settings: PublicChatSettings | None = None,
    embedding_service: OpenAIPublicEmbeddingService | None = None,
) -> ConsultaTurnRunner:
    """Alias de compatibilidade phase2."""
    return build_public_chat_runner(
        pool=pool,
        llm_provider=llm_provider,
        settings=settings,
        embedding_service=embedding_service,
    )

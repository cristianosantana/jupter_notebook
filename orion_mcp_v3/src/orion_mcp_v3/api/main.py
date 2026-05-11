"""
FastAPI application (Fase 6.1 + 7.1) — ponto de entrada da API de produto.

Usa :func:`~orion_mcp_v3.config.settings.get_settings` para configuração central.

Uso:
    uvicorn orion_mcp_v3.api.main:app --reload
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from orion_mcp_v3.api.models import HealthResponse
from orion_mcp_v3.api.routes.chat import create_chat_router
from orion_mcp_v3.config.settings import OrionSettings, get_settings
from orion_mcp_v3.protocols.llm import LLMProvider, NullLLMProvider
from orion_mcp_v3.runtime.attention_policy import AttentionPolicy
from orion_mcp_v3.runtime.narrator import CognitiveNarrator
from orion_mcp_v3.runtime.session_manager import SessionManager


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
                temperature=settings.llm_temperature,
                max_tokens=settings.llm_max_tokens,
                base_url=settings.llm_base_url or None,
            )
        except ImportError:
            pass
    return NullLLMProvider()


def create_app(
    *,
    llm_provider: LLMProvider | None = None,
    session_manager: SessionManager | None = None,
    settings: OrionSettings | None = None,
) -> FastAPI:
    """Factory da aplicação FastAPI com dependências injectáveis."""
    s = settings or get_settings()

    app = FastAPI(
        title="Orion Cognitive Copilot",
        version="0.7.0",
        description="Runtime cognitivo orientado a contexto — API de produto.",
        debug=s.api_debug,
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
    sm = session_manager or SessionManager(
        default_token_budget=s.max_tokens,
        default_policy=default_policy,
        memory_window=s.memory_window,
    )
    narrator = CognitiveNarrator(provider)

    chat_router = create_chat_router(
        session_manager=sm,
        llm_provider=provider,
        narrator=narrator,
    )
    app.include_router(chat_router)

    @app.get("/health", response_model=HealthResponse, tags=["infra"])
    async def health() -> HealthResponse:
        return HealthResponse()

    return app


app = create_app()

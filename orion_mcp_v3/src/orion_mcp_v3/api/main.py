"""
FastAPI application (Fase 6.1) — ponto de entrada da API de produto.

Uso:
    uvicorn orion_mcp_v3.api.main:app --reload
"""

from __future__ import annotations

from fastapi import FastAPI

from orion_mcp_v3.api.models import HealthResponse
from orion_mcp_v3.api.routes.chat import create_chat_router
from orion_mcp_v3.protocols.llm import LLMProvider, NullLLMProvider
from orion_mcp_v3.runtime.narrator import CognitiveNarrator
from orion_mcp_v3.runtime.session_manager import SessionManager


def create_app(
    *,
    llm_provider: LLMProvider | None = None,
    session_manager: SessionManager | None = None,
) -> FastAPI:
    """Factory da aplicação FastAPI com dependências injectáveis."""
    app = FastAPI(
        title="Orion Cognitive Copilot",
        version="0.6.0",
        description="Runtime cognitivo orientado a contexto — API de produto.",
    )

    provider = llm_provider or NullLLMProvider()
    sm = session_manager or SessionManager()
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

"""
Modelos Pydantic para request/response da API de chat (Fase 6.1).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Payload de entrada para ``POST /api/v1/chat``."""

    message: str = Field(..., min_length=1, max_length=8000, description="Mensagem do utilizador.")
    conversation_id: str | None = Field(None, description="ID da sessão (criado se ausente).")
    stream: bool = Field(False, description="Se True, resposta em SSE streaming.")
    max_tokens: int = Field(4096, ge=64, le=32000, description="Orçamento de tokens para o prompt.")
    policy: str = Field("balanced", description="Política de atenção (balanced, analytical, memory_focused, ...).")


class UsageInfo(BaseModel):
    """Consumo de tokens reportado pelo LLM."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatResponseMeta(BaseModel):
    """Metadados da resposta."""

    conversation_id: str
    model: str = ""
    finish_reason: str = "stop"
    latency_ms: float = 0.0
    usage: UsageInfo = Field(default_factory=UsageInfo)
    safeguards: list[str] = Field(default_factory=list)
    cognitive_intent: str | None = None
    coverage_note: str = ""


class ChatResponse(BaseModel):
    """Payload de saída de ``POST /api/v1/chat``."""

    reply: str
    meta: ChatResponseMeta


class ErrorResponse(BaseModel):
    """Payload de erro genérico."""

    error: str
    detail: str = ""


class HealthResponse(BaseModel):
    """Payload do health check."""

    status: str = "ok"
    version: str = "0.6.0"

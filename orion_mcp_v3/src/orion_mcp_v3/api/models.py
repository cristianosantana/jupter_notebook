"""
Modelos Pydantic para request/response da API de chat (Fase 6.1).
"""

from __future__ import annotations

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


class StoredChatMessage(BaseModel):
    """Mensagem tal como persistida (alinhado ao JSONB em ``conversation_state.messages``)."""

    role: str
    content: str
    created_at: str = Field(..., description="ISO-8601 com offset (ex.: +00:00).")
    message_id: int


class SessionListItem(BaseModel):
    """Uma sessão listável com histórico completo de mensagens (sem truncar conteúdo)."""

    conversation_id: str
    turn_count: int = 0
    messages: list[StoredChatMessage] = Field(default_factory=list)


class SessionListResponse(BaseModel):
    """Lista de sessões para ``GET /api/v1/sessions``."""

    sessions: list[SessionListItem]


class ChatOptionsResponse(BaseModel):
    """Opções alinhadas ao backend (políticas + limites ``max_tokens`` do ``ChatRequest``)."""

    policies: list[str]
    max_tokens_min: int = 64
    max_tokens_max: int = 32000
    max_tokens_presets: list[int] = Field(
        default_factory=lambda: [2048, 4096, 8192, 16384, 20000, 32000],
        description="Sugestões de orçamento (dentro do intervalo permitido pelo chat).",
    )
    default_max_tokens: int = 4096
    default_policy: str = "balanced"

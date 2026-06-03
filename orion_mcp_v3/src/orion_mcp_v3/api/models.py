"""
Modelos Pydantic para request/response da API de chat (Fase 6.1).
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

_EMAIL_RX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class ChatRequest(BaseModel):
    """Payload de entrada para ``POST /api/v1/chat``."""

    message: str = Field(..., min_length=1, max_length=8000, description="Mensagem do utilizador.")
    conversation_id: str | None = Field(None, description="ID da sessão (criado se ausente).")
    stream: bool = Field(False, description="Se True, resposta em SSE streaming.")
    max_tokens: int = Field(4096, ge=64, le=32000, description="Orçamento de tokens para o prompt.")
    policy: str = Field("balanced", description="Política de atenção (balanced, analytical, memory_focused, ...).")
    email_to: str | None = Field(None, description="Destinatário para envio opcional da resposta por e-mail.")
    email_subject: str | None = Field(None, max_length=200, description="Assunto opcional do e-mail.")

    @field_validator("email_to")
    @classmethod
    def _validate_email_to(cls, value: str | None) -> str | None:
        if value is None:
            return None
        email = value.strip()
        if not email:
            return None
        if not _EMAIL_RX.match(email):
            raise ValueError("email_to inválido")
        return email

    @field_validator("email_subject")
    @classmethod
    def _normalize_email_subject(cls, value: str | None) -> str | None:
        if value is None:
            return None
        subject = value.strip()
        return subject or None


class UsageInfo(BaseModel):
    """Consumo de tokens reportado pelo LLM."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class EmailDeliveryInfo(BaseModel):
    """Status seguro do envio opcional por e-mail."""

    status: Literal["not_requested", "sent", "skipped", "failed"] = "not_requested"
    to: str | None = None
    message: str = ""


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
    email_delivery: EmailDeliveryInfo = Field(default_factory=EmailDeliveryInfo)


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

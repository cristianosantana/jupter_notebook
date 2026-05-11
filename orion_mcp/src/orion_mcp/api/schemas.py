from __future__ import annotations

from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator

from orion_mcp.core.config.settings import get_settings
from orion_mcp.core.strategy import Strategy
from orion_mcp.mcp_adapter.queries import ALLOWED_QUERY_IDS


class ChatRequest(BaseModel):
    session_id: str | None = Field(
        default=None,
        max_length=128,
        description="Chave da conversa; se omitido ou vazio, o servidor gera um UUID.",
    )
    message: str = Field(min_length=1, max_length=16000)
    strategy: Literal["fast", "deep"] = "fast"
    query_id: str | None = Field(
        default=None,
        description="Identificador de consulta catalogada no MCP (requer gRPC na API).",
    )
    date_from: str | None = Field(default=None, description="YYYY-MM-DD (opcional).")
    date_to: str | None = Field(default=None, description="YYYY-MM-DD (opcional).")
    limit: int | None = Field(
        default=None,
        ge=1,
        le=10000,
        description="LIMIT na consulta catalogada (opcional).",
    )
    offset: int | None = Field(default=None, ge=0, description="OFFSET (opcional).")
    summarize: bool | None = Field(
        default=None,
        description="Modo compacto MCP (opcional); por defeito true no servidor.",
    )

    @field_validator("session_id", mode="before")
    @classmethod
    def _normalize_session_id(cls, v: object) -> str | None:
        if v is None:
            return None
        if isinstance(v, str):
            s = v.strip()
            return s or None
        return v

    @field_validator("query_id", "date_from", "date_to", mode="before")
    @classmethod
    def _strip_optional_str(cls, v: object) -> str | None:
        if v is None:
            return None
        if isinstance(v, str):
            s = v.strip()
            return s or None
        return v

    @field_validator("query_id")
    @classmethod
    def _query_id_allowed(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if v not in ALLOWED_QUERY_IDS:
            raise ValueError(f"query_id não permitido: {v!r}")
        return v

    @model_validator(mode="after")
    def _domain_requires_grpc(self) -> ChatRequest:
        if self.query_id and not (get_settings().mcp_grpc_target or "").strip():
            raise ValueError(
                "Consultas catalogadas (query_id) requerem ORION_MCP_GRPC_TARGET configurado na API."
            )
        return self

    def resolved_session_id(self) -> str:
        if self.session_id:
            return self.session_id
        return str(uuid4())


class ChatResponse(BaseModel):
    session_id: str
    payload: dict
    metrics: dict

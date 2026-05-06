from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class ChatRequestV2(BaseModel):
    message: str = Field(..., min_length=1)
    session_id: str | None = Field(
        default=None,
        description="Opcional na primeira mensagem; omitir cria nova sessão no servidor.",
    )
    user_id: str | None = Field(
        default=None,
        description="Opcional; omitir gera utilizador anónimo ou recupera da sessão existente.",
    )
    date_from: str | None = Field(default=None, description="YYYY-MM-DD")
    date_to: str | None = Field(default=None, description="YYYY-MM-DD")

    @field_validator("session_id", "user_id", mode="before")
    @classmethod
    def _strip_optional(cls, v: object) -> str | None:
        if v is None:
            return None
        if isinstance(v, str):
            s = v.strip()
            return s if s else None
        raise TypeError("session_id e user_id devem ser strings ou omitidos")

    @field_validator("session_id")
    @classmethod
    def _session_len(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if len(v) < 4:
            raise ValueError("session_id deve ter pelo menos 4 caracteres quando enviado")
        return v

    @field_validator("user_id")
    @classmethod
    def _user_len(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if len(v) < 1:
            raise ValueError("user_id inválido quando enviado")
        return v


class ChatResponseV2(BaseModel):
    reply: str
    session_id: str
    user_id: str
    metadata: dict

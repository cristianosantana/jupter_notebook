from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ORION_V2_",
        env_file=(".env", _PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "orion_mcp_v2"
    env: Literal["development", "staging", "production"] = "development"
    debug: bool = False
    log_level: str = "INFO"

    database_url: str = Field(
        default="postgresql://orion:orion@localhost:5432/orion_v2",
        description="asyncpg URL",
    )
    db_required: bool = False

    mysql_url: str | None = Field(default=None, description="mysql://user:pass@host:3306/db")

    redis_url: str | None = Field(default=None)

    openai_api_key: str | None = None
    openai_model: str = "gpt-5-mini"
    openai_max_tokens: int = 4096
    openai_timeout_seconds: float = 120.0

    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    consolidation_hour: int = 3
    consolidation_minute: int = 0
    memory_curta_ttl_seconds: int = 604800
    session_retention_days: int = 30

    rate_limit_per_minute: int = 60

    context_section_budget_tokens: int = 4000
    llm_prompt_token_budget: int | None = Field(
        default=None,
        description="Se definido, substitui o teto estimado de tokens do prompt.",
    )
    llm_context_max_chars: int | None = Field(
        default=None,
        description="Teto total system+user em caracteres (opcional).",
    )
    max_llm_calls_per_request: int = Field(default=2, ge=1, le=32)
    max_tool_calls_per_request: int = Field(default=8, ge=0, le=256)

    otel_enabled: bool = Field(default=False, description="ORION_V2_OTEL_ENABLED semantics via env")

    llm_io_dump_enabled: bool = Field(
        default=False,
        description="Se true, grava JSON por chamada LLM (pedido + resposta bruta) em llm_io_dump_dir.",
    )
    llm_io_dump_dir: Path = Field(
        default=Path("/tmp/orion_mcp_v2_llm_io"),
        description="Directório para ficheiros llm_io_*.json (em Docker, monte um volume se quiser ver no host).",
    )

    skill_system_prompt_max_chars: int = Field(
        default=120_000,
        ge=1024,
        le=500_000,
        description="Teto para validação do system_prompt em YAML (testes / CI).",
    )

    reference_lookups_enabled: bool = Field(
        default=True,
        description="Anexar automaticamente skill/reference_lookups.md ao system prompt.",
    )
    reference_lookups_max_chars: int = Field(
        default=48_000,
        ge=0,
        le=500_000,
        description="Tamanho máximo do bloco de lookups (0 = omitir).",
    )
    reference_lookups_file: Path | None = Field(
        default=None,
        description="Caminho opcional para substituir o ficheiro embutido reference_lookups.md.",
    )

    @field_validator("llm_context_max_chars", mode="after")
    @classmethod
    def _clamp_llm_context_max_chars(cls, v: int | None) -> int | None:
        if v is None:
            return None
        if v < 1:
            raise ValueError("llm_context_max_chars must be >= 1 when set")
        return v

    @property
    def effective_prompt_token_budget(self) -> int:
        if self.llm_prompt_token_budget is not None:
            raw = self.llm_prompt_token_budget
        else:
            raw = min(self.context_section_budget_tokens, 8000)
        return max(256, min(8000, int(raw)))

    @property
    def is_production(self) -> bool:
        return self.env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()

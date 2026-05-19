"""
Configuração central (Fase 7.1) — pydantic-settings.

Lê de variáveis de ambiente com prefixo ``ORION_`` (ex.: ``ORION_MYSQL_URL``)
ou de ficheiro ``.env`` quando presente. Fallbacks seguros para desenvolvimento local.

Uso::

    from orion_mcp_v3.config.settings import get_settings
    s = get_settings()
    print(s.mysql_url, s.llm_model, s.max_tokens)
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class OrionSettings(BaseSettings):
    """Configuração centralizada do Orion v3 — fonte única de verdade."""

    model_config = SettingsConfigDict(
        env_prefix="ORION_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ── Bases de dados ───────────────────────────────────────────────
    mysql_url: str = Field(
        "",
        description="URL MySQL (mysql://user:pass@host:3306/db). Vazio = desabilitado.",
    )
    postgres_url: str = Field(
        "",
        description="URL PostgreSQL (postgres://user:pass@host:5432/db). Vazio = desabilitado.",
    )
    redis_url: str = Field(
        "",
        description="URL Redis (redis://host:6379/0). Vazio = desabilitado.",
    )

    # ── Pool sizes ───────────────────────────────────────────────────
    mysql_pool_min: int = Field(1, ge=1)
    mysql_pool_max: int = Field(10, ge=1)
    postgres_pool_min: int = Field(1, ge=1)
    postgres_pool_max: int = Field(10, ge=1)

    # ── LLM ──────────────────────────────────────────────────────────
    llm_model: str = Field("gpt-5-mini", description="Modelo LLM default.")
    llm_api_key: str = Field("", description="API key do provider LLM.")
    llm_base_url: str = Field("", description="Base URL alternativa (ex.: Azure, proxy).")
    llm_max_tokens: int = Field(2048, ge=64, le=128000)

    # ── Runtime cognitivo ────────────────────────────────────────────
    max_tokens: int = Field(4096, ge=64, le=128000, description="Orçamento default do prompt.")
    default_limit: int = Field(500, ge=1, description="LIMIT default em queries SQL.")
    default_policy: str = Field("balanced", description="AttentionPolicy default.")
    memory_window: int = Field(60, ge=1, description="Mensagens recentes na memory window.")
    session_list_max_messages: int = Field(
        50_000,
        ge=1,
        le=1_000_000,
        description="Máximo de mensagens por sessão em GET /api/v1/sessions (histórico listado).",
    )

    # ── Timeouts (segundos) ──────────────────────────────────────────
    mysql_timeout: float = Field(30.0, ge=1.0)
    postgres_timeout: float = Field(30.0, ge=1.0)
    redis_timeout: float = Field(5.0, ge=0.5)
    llm_timeout: float = Field(60.0, ge=5.0)

    # ── API ──────────────────────────────────────────────────────────
    api_host: str = Field("0.0.0.0", description="Host para uvicorn.")
    api_port: int = Field(8000, ge=1, le=65535)
    api_debug: bool = Field(False, description="Modo debug (reload, logs verbosos).")
    api_cors_origins: str = Field("*", description="Origins CORS (separados por vírgula).")

    # ── Observabilidade ──────────────────────────────────────────────
    log_level: str = Field("INFO", description="Nível de log (DEBUG, INFO, WARNING, ERROR).")
    log_format: str = Field("json", description="Formato de log (json ou text).")
    trace_enabled: bool = Field(False, description="Habilitar tracing distribuído.")
    analytics_pipeline_trace: bool = Field(
        False,
        description="JSON por linha em orion.analytics.pipeline: pré/pós de intent, memória, analytics, fusão, narração.",
    )
    analytics_pipeline_log_dir: str = Field(
        "",
        description=(
            "Directório para ficheiros analytics_pipeline_<UTC>.jsonl (uma linha = um JSON). "
            "Usado apenas se analytics_pipeline_trace=true. Caminho relativo = relativamente ao cwd."
        ),
    )

    # ── Helpers ──────────────────────────────────────────────────────

    @property
    def mysql_enabled(self) -> bool:
        return bool(self.mysql_url.strip())

    @property
    def postgres_enabled(self) -> bool:
        return bool(self.postgres_url.strip())

    @property
    def redis_enabled(self) -> bool:
        return bool(self.redis_url.strip())

    @property
    def llm_enabled(self) -> bool:
        return bool(self.llm_api_key.strip())

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.api_cors_origins.split(",") if o.strip()]


@lru_cache(maxsize=1)
def get_settings() -> OrionSettings:
    """Singleton cacheado — usa variáveis de ambiente / ``.env``."""
    return OrionSettings()


def get_settings_uncached(**overrides: Any) -> OrionSettings:
    """Instância nova (para testes ou reconfiguração dinâmica)."""
    if "_env_file" not in overrides:
        overrides.setdefault("_env_file", None)
    return OrionSettings(**overrides)

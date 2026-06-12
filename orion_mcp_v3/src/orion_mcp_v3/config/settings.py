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

import os
from functools import lru_cache
from typing import Any, Literal

from pydantic import Field, field_validator
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

    # ── E-mail ───────────────────────────────────────────────────────
    email_enabled: bool = Field(False, description="Habilitar envio de respostas do chat por e-mail.")
    email_drive: str = Field("", description="Driver de e-mail legado/compatível (ex.: smtp, mailgun).")
    email_driver: str = Field("", description="Driver de e-mail (ex.: smtp, mailgun).")
    email_host: str = Field("", description="Host do provedor de e-mail.")
    email_port: int | None = Field(None, ge=1, le=65535)
    email_username: str = Field("", description="Usuário do provedor de e-mail; vazio = sem autenticação.")
    email_password: str = Field("", description="Senha/token do provedor de e-mail; nunca deve ser logada.")
    email_smtp_host: str = Field("", description="Host SMTP para envio de e-mail.")
    email_smtp_port: int = Field(587, ge=1, le=65535)
    email_smtp_username: str = Field("", description="Usuário SMTP; vazio = sem autenticação.")
    email_smtp_password: str = Field("", description="Senha SMTP; nunca deve ser logada.")
    email_from_address: str = Field("", description="Endereço remetente usado pelo Orion.")
    email_from_name: str = Field("Orion", description="Nome exibido do remetente.")
    mailgun_domain: str = Field("", description="Domínio Mailgun (ex.: mg.example.com).")
    mailgun_secret: str = Field("", description="API key/secret do Mailgun; nunca deve ser logada.")
    mail_from_name: str = Field("", description="Nome exibido do remetente para provedores de e-mail HTTP.")
    mailgun_endpoint: str = Field("https://api.mailgun.net/v3", description="Endpoint base da API Mailgun.")
    email_start_tls: bool = Field(True, description="Usar STARTTLS ao conectar no SMTP.")
    email_timeout: float = Field(10.0, ge=1.0, description="Timeout SMTP em segundos.")
    email_parsing_profile: Literal["default", "minimal", "executive"] = Field(
        "default",
        description="Perfil de exibição do e-mail: default (completo), minimal (só resposta direta), executive (sem complementar).",
    )

    # ── Runtime cognitivo ────────────────────────────────────────────
    max_tokens: int = Field(4096, ge=64, le=128000, description="Orçamento default do prompt.")
    default_limit: int = Field(500, ge=1, description="LIMIT default em queries SQL.")
    default_policy: str = Field("analytical", description="AttentionPolicy default.")
    memory_window: int = Field(60, ge=1, description="Mensagens recentes na memory window.")
    session_list_max_messages: int = Field(
        50_000,
        ge=1,
        le=1_000_000,
        description="Máximo de mensagens por sessão em GET /api/v1/sessions (histórico listado).",
    )

    # ── Embeddings (chat_turn_embeddings — experimental) ─────────────
    embedding_mode: Literal["off", "index_only", "retrieve"] = Field(
        "off",
        description=(
            "off: sem embeddings; index_only: grava turnos sem busca vectorial; "
            "retrieve: indexa e usa VectorRetriever em paralelo com retrieval lexical."
        ),
    )
    embedding_enabled: bool = Field(
        False,
        description="Legado: se true e embedding_mode=off, trata como retrieve.",
    )
    embedding_model: str = Field(
        "text-embedding-3-small",
        description="Modelo de embeddings (OpenAI).",
    )
    embedding_dimensions: int = Field(1536, ge=1, le=3072)
    embedding_top_k: int = Field(5, ge=1, le=50)

    @field_validator("embedding_mode", mode="before")
    @classmethod
    def _normalize_embedding_mode(cls, v: object) -> str:
        if v is None:
            return "off"
        s = str(v).strip().lower()
        if s in ("off", "index_only", "retrieve"):
            return s
        return "off"

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
    def email_configured(self) -> bool:
        """Envio de e-mail disponível sem expor credenciais."""
        if self.email_driver_name == "mailgun":
            return (
                self.email_enabled
                and bool(self.effective_email_host.strip())
                and bool(self.effective_email_password)
                and bool(self.email_from_address.strip())
            )
        return (
            self.email_enabled
            and bool(self.effective_email_host.strip())
            and bool(self.email_from_address.strip())
        )

    @property
    def email_driver_name(self) -> str:
        """Driver normalizado; ``ORION_EMAIL_DRIVE`` é aceito por compatibilidade."""
        return (self.email_driver or self.email_drive or "smtp").strip().lower() or "smtp"

    @property
    def effective_email_host(self) -> str:
        if self.email_driver_name == "mailgun":
            return self._field_or_env(self.mailgun_domain, "MAILGUN_DOMAIN").strip()
        if self.email_driver_name == "smtp" and self.email_smtp_host.strip():
            return self.email_smtp_host.strip()
        return self.email_host.strip() or self.email_smtp_host.strip()

    @property
    def effective_email_port(self) -> int:
        if self.email_driver_name == "smtp" and self.email_smtp_port != 587:
            return self.email_smtp_port
        return self.email_port if self.email_port is not None else self.email_smtp_port

    @property
    def effective_email_username(self) -> str:
        if self.email_driver_name == "mailgun":
            return self.email_username.strip()
        if self.email_driver_name == "smtp" and self.email_smtp_username.strip():
            return self.email_smtp_username.strip()
        return self.email_username.strip() or self.email_smtp_username.strip()

    @property
    def effective_email_password(self) -> str:
        if self.email_driver_name == "mailgun":
            return self._field_or_env(self.mailgun_secret, "MAILGUN_SECRET")
        if self.email_driver_name == "smtp" and self.email_smtp_password:
            return self.email_smtp_password
        return self.email_password or self.email_smtp_password

    @property
    def effective_email_from_name(self) -> str:
        if self.email_driver_name == "mailgun":
            return self._field_or_env(self.mail_from_name, "MAIL_FROM_NAME").strip() or self.email_from_name
        return self.email_from_name

    @property
    def effective_mailgun_endpoint(self) -> str:
        default_endpoint = "https://api.mailgun.net/v3"
        endpoint = self.mailgun_endpoint.strip()
        if endpoint == default_endpoint:
            endpoint = os.getenv("MAILGUN_ENDPOINT", "").strip() or endpoint
        return endpoint.rstrip("/") or "https://api.mailgun.net/v3"

    @staticmethod
    def _field_or_env(field_value: str, env_name: str) -> str:
        return field_value.strip() or os.getenv(env_name, "").strip()

    @property
    def effective_embedding_mode(self) -> Literal["off", "index_only", "retrieve"]:
        """Modo efectivo; ``embedding_enabled=true`` sem modo explícito → ``retrieve``."""
        if self.embedding_mode != "off":
            return self.embedding_mode
        if self.embedding_enabled:
            return "retrieve"
        return "off"

    @property
    def embedding_active(self) -> bool:
        """API key presente e modo não-off (indexação ou retrieval)."""
        return self.effective_embedding_mode != "off" and bool(self.llm_api_key.strip())

    @property
    def embedding_should_index(self) -> bool:
        return self.embedding_active and self.effective_embedding_mode in ("index_only", "retrieve")

    @property
    def embedding_should_retrieve(self) -> bool:
        return self.embedding_active and self.effective_embedding_mode == "retrieve"

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

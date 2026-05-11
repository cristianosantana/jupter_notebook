from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Heurística alinhada a `context_builder._estimate_tokens` (len//4).
_CHARS_PER_TOKEN_ESTIMATE: int = 4
# Fracção do orçamento de tokens (estimado) dedicada ao texto catalogado quando
# `tool_llm_summary_max_chars` não é definido explicitamente.
_TOOL_SUMMARY_CHAR_SHARE: float = 0.6

# Raiz do pacote `orion_mcp` no repo (directório que contém `src/`, `.env`, etc.)
_ORION_PROJECT_ROOT = Path(__file__).resolve().parents[4]


def _default_llm_debug_log_dir() -> str:
    return str(_ORION_PROJECT_ROOT / "logs")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ORION_",
        # 1º `.env` no CWD; depois `.env` na raiz do projecto (último ganha — típico `orion_mcp/.env`).
        env_file=(".env", _ORION_PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    # Usar apenas ORION_ENV (prefixo ORION_). Evitar alias "ENV" — conflita com ENV=production comum em shells/CI.
    env: Literal["development", "staging", "production"] = Field(default="development")
    api_enable_legacy_chat_alias: bool = False

    database_url: str = Field(
        default="postgresql://orion:orion@localhost:5432/orion",
        description="Async PostgreSQL URL (asyncpg)",
    )
    db_required: bool = Field(default=False)

    redis_url: str | None = None

    openai_api_key: str | None = None
    openai_http_timeout_seconds: float = Field(
        default=60.0,
        ge=1.0,
        le=600.0,
        description="Timeout HTTP total no cliente OpenAI (chat + embeddings quando key definida).",
    )
    llm_model_fast: str = "gpt-5-mini"
    llm_model_reasoning: str = "gpt-5"
    embedding_model: str = "text-embedding-3-large"
    embedding_dimensions: int = 1536

    max_llm_calls_per_request: int = 2
    max_tool_calls_per_request: int = 1
    context_max_tokens: int = Field(
        default=3500,
        description=(
            "Legado: usado com `llm_max_prompt_tokens` como `min(...)` quando "
            "`llm_prompt_token_budget` (ORION_LLM_PROMPT_TOKEN_BUDGET) está vazio."
        ),
    )
    context_section_budget_tokens: int = Field(
        default=4000,
        description=(
            "Teto estimado em tokens para a soma das secções em `build_context`; "
            "o valor efectivo é `min(context_section_budget_tokens, effective_prompt_token_budget)`."
        ),
    )
    llm_max_prompt_tokens: int = Field(
        default=3000,
        ge=256,
        le=8000,
        description=(
            "Legado: usado com `context_max_tokens` como `min(...)` quando "
            "`llm_prompt_token_budget` está vazio. Preferir ORION_LLM_PROMPT_TOKEN_BUDGET."
        ),
    )
    llm_prompt_token_budget: int | None = Field(
        default=None,
        description=(
            "Teto canónico (tokens estimados) para o prompt de contexto + `cap_llm_prompt`. "
            "Env: ORION_LLM_PROMPT_TOKEN_BUDGET. Se omitido, usa-se min(context_max_tokens, llm_max_prompt_tokens)."
        ),
    )
    llm_completion_max_tokens: int = Field(
        default=4096,
        ge=64,
        le=8192,
        description=(
            "Parâmetro `max_tokens` / `max_completion_tokens` na geração da resposta do modelo (chat); "
            "independente do teto de contexto/prompt. Valor mais alto por defeito para modelos com "
            "raciocínio interno (ex.: gpt-5) não ficarem sem texto visível com 1024."
        ),
    )
    llm_insights_max_tokens: int = Field(
        default=900,
        ge=64,
        le=8192,
        description="Teto de tokens na chamada LLM do pacote insights (JSON insights+reply).",
    )
    llm_context_max_chars: int | None = Field(
        default=None,
        description=(
            "Por pedido HTTP ao chat: teto em caracteres para len(system_prompt)+len(contexto user). "
            "None = não aplicar este corte (continuam os tetos por tokens). "
            "Env: ORION_LLM_CONTEXT_MAX_CHARS."
        ),
    )
    llm_system_prompt: str = Field(
        default=(
            "És o assistente de analytics da plataforma Orion MCP. "
            "Usa apenas a informação nas secções de contexto (em especial «Dados resumidos»). "
            "Não inventes números, entidades ou factos não suportados pelos dados. "
            "Quando a postura de risco for «conservador» (perfil heurístico ou pergunta «porquê»), "
            "limita a especulação e declara incerteza. "
            "Não existe garantia de verdade absoluta: podes errar; indica limitações quando aplicável. "
            "Prioriza simplicidade e pragmatismo: resposta útil e próximos passos concretos quando fizer sentido. "
            "Quando «Dados resumidos» incluir resultado de consulta catalogada, não proponhas SQL nem código para "
            "substituir essa execução: sintetiza o que já vem no resumo."
        ),
        description="Mensagem system do chat (OpenAI). Ver docs/heurística_de_tomada_de_decisão.md e task_profile.",
    )
    llm_halt_before_chat: bool = Field(
        default=False,
        description=(
            "Se true, não chama o LLM no chat (resposta + insights); grava o pedido em "
            "`llm_debug_log_dir` e devolve mensagem de parada. Desactivar para produção."
        ),
    )
    llm_debug_log_dir: str = Field(
        default_factory=_default_llm_debug_log_dir,
        description="Directório para ficheiros JSON de depuração do pedido LLM (criado se não existir).",
    )
    orchestrator_chat_trace: bool = Field(
        default=False,
        description=(
            "Se true, regista linhas JSON em log INFO (logger orion_mcp.orchestration) após "
            "`_prepare_turn` e antes do dump de parada LLM."
        ),
    )

    @field_validator("orchestrator_chat_trace", mode="before")
    @classmethod
    def _coerce_orchestrator_chat_trace(cls, v: object) -> bool:
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            s = v.strip().lower()
            if s in ("1", "true", "yes", "on"):
                return True
            if s in ("0", "false", "no", "off", ""):
                return False
            return False
        return bool(v)

    @field_validator("llm_prompt_token_budget", mode="after")
    @classmethod
    def _clamp_llm_prompt_token_budget(cls, v: int | None) -> int | None:
        if v is None:
            return None
        return max(256, min(8000, int(v)))

    @field_validator("llm_context_max_chars", mode="after")
    @classmethod
    def _clamp_llm_context_max_chars(cls, v: int | None) -> int | None:
        if v is None:
            return None
        n = int(v)
        if n < 1:
            raise ValueError("llm_context_max_chars must be >= 1 when set")
        return n

    @field_validator("llm_halt_before_chat", mode="before")
    @classmethod
    def _coerce_llm_halt_before_chat(cls, v: object) -> bool:
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            s = v.strip().lower()
            if s in ("1", "true", "yes", "on"):
                return True
            if s in ("0", "false", "no", "off", ""):
                return False
            return False
        return bool(v)
    tool_timeout_seconds: float = 10.0

    # --- MCP serviço em rede (gRPC) + cache L1 curto na API ---
    mcp_grpc_target: str | None = Field(
        default=None,
        description="ex.: mcp-grpc:50051 — se definido, tools pesadas usam cliente gRPC em vez de in-process.",
    )

    @field_validator("mcp_grpc_target", mode="before")
    @classmethod
    def _normalize_mcp_grpc_target(cls, v: object) -> str | None:
        if v is None:
            return None
        if isinstance(v, str):
            s = v.strip()
            return s or None
        return v

    mcp_grpc_deadline_seconds: float = Field(default=5.0, ge=0.5, le=120.0)
    mcp_grpc_use_tls: bool = Field(
        default=False,
        description="Em produção, usar TLS/mTLS no canal gRPC (credenciais fora de query string).",
    )
    mcp_grpc_retry_count: int = Field(default=1, ge=0, le=5, description="Retries só para erros transitórios.")
    mcp_grpc_circuit_failure_threshold: int = Field(default=5, ge=1, le=100)
    mcp_grpc_circuit_open_seconds: float = Field(default=30.0, ge=1.0, le=600.0)
    mcp_l1_tool_cache_ttl_seconds: int = Field(
        default=300,
        ge=10,
        le=86400,
        description="TTL curto do cache L1 (API) quando o resultado vem do MCP remoto.",
    )

    tool_llm_preview_rows: int = Field(
        default=10,
        ge=1,
        le=10000,
        description=(
            "Linhas completas máx. na pré-visualização enviada ao LLM (DataInterpreter). "
            "No serviço MCP (gRPC), com summarize=true, limita também quantas linhas da página "
            "entram em rows_sample (alinhado ao teto de limit da consulta). "
            "Ignorado para `rows` quando `tool_llm_catalog_full_rows` está activo (envia todas as linhas do payload)."
        ),
    )
    tool_llm_catalog_full_rows: bool = Field(
        default=False,
        description=(
            "Se true: para consultas catalogadas com `rows` no payload, o DataInterpreter inclui "
            "**todas** as linhas devolvidas pela tool (até ao limite de caracteres efectivo). "
            "O teto de caracteres sobe com `ORION_LLM_CONTEXT_MAX_CHARS` quando definido. "
            "Env: ORION_TOOL_LLM_CATALOG_FULL_ROWS."
        ),
    )
    tool_llm_summary_max_chars: int | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "tool_llm_summary_max_chars",
            "llm_tool_context_chars",
        ),
        description=(
            "Teto de caracteres para o texto catalogado no DataInterpreter "
            "(ORION_TOOL_LLM_SUMMARY_MAX_CHARS ou ORION_LLM_TOOL_CONTEXT_CHARS). "
            "None = derivado do orçamento de prompt (ver código: CHAR_SHARE)."
        ),
    )
    tool_domain_default_limit: int = Field(
        default=200,
        ge=1,
        le=10000,
        description="LIMIT por defeito no ramo chat para run_domain_query (paginação MCP).",
    )
    tool_domain_default_summarize: bool = Field(
        default=True,
        description="summarize=true por defeito no pedido run_domain_query via chat.",
    )
    mcp_debug_stdout: bool = Field(
        default=False,
        description="Se true, emite prints [ORION_MCP] no stdout (API/registry/executor).",
    )

    enable_long_memory: bool = False
    enable_memory_index_worker: bool = Field(
        default=True,
        description="Se true, enfileira embed+INSERT após respostas de chat (Celery).",
    )
    memory_ivfflat_lists: int = Field(
        default=100,
        ge=2,
        le=10000,
        description="Parâmetro lists do índice IVFFlat (migração 004; dimensões >2000).",
    )

    celery_broker_url: str = "redis://localhost:6379/1"

    @property
    def effective_prompt_token_budget(self) -> int:
        """Teto único de tokens (estimados) para prompt de contexto e `cap_llm_prompt`."""
        if self.llm_prompt_token_budget is not None:
            raw = self.llm_prompt_token_budget
        else:
            raw = min(self.context_max_tokens, self.llm_max_prompt_tokens)
        return max(256, min(8000, int(raw)))

    def resolved_tool_llm_summary_max_chars(self) -> int:
        """Teto efectivo de caracteres para o DataInterpreter (sempre int)."""
        eff = self.effective_prompt_token_budget
        if self.tool_llm_summary_max_chars is not None:
            n = int(self.tool_llm_summary_max_chars)
        else:
            n = int(eff * _CHARS_PER_TOKEN_ESTIMATE * _TOOL_SUMMARY_CHAR_SHARE)
        return max(2000, min(100_000, n))

    def effective_tool_llm_summary_max_chars(self) -> int:
        """
        Teto passado ao `tool_result_to_llm_summary` para consultas catalogadas.
        Com `tool_llm_catalog_full_rows`, alarga o orçamento (ligado a `llm_context_max_chars`).
        """
        base = self.resolved_tool_llm_summary_max_chars()
        if not self.tool_llm_catalog_full_rows:
            return base
        cap = self.llm_context_max_chars
        if cap is not None:
            return max(base, min(2_000_000, int(cap * 0.78)))
        return max(base, 750_000)

    @field_validator("tool_llm_summary_max_chars", mode="after")
    @classmethod
    def _clamp_tool_llm_summary_max_chars(cls, v: int | None) -> int | None:
        if v is None:
            return None
        return max(2000, min(100_000, int(v)))

    @model_validator(mode="after")
    def _long_memory_and_unified_limits(self) -> Settings:
        db = (self.database_url or "").strip()
        if self.enable_long_memory and not db:
            raise ValueError("enable_long_memory requires database_url")
        if self.tool_llm_summary_max_chars is None:
            rc = self.resolved_tool_llm_summary_max_chars()
            object.__setattr__(self, "tool_llm_summary_max_chars", rc)
        return self

    @field_validator("embedding_dimensions")
    @classmethod
    def _dims(cls, v: int) -> int:
        if v not in (256, 512, 1024, 1536, 2000, 3072):
            raise ValueError("embedding_dimensions must be a supported OpenAI size")
        return v

    @property
    def is_production(self) -> bool:
        return self.env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()

from functools import lru_cache
from uuid import UUID

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict  # pyright: ignore[reportMissingImports]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: str = ""
    openai_model: str = ""

    mysql_host: str = "localhost"
    mysql_port: int = 3306
    mysql_user: str = ""
    mysql_password: str = ""
    mysql_database: str = ""

    # PostgreSQL — sessões e utilizadores (transcript de especialistas)
    postgres_host: str = ""
    postgres_port: int = 5432
    postgres_user: str = ""
    postgres_password: str = ""
    postgres_database: str = "maestro_sessions"
    # Base onde ligar para ``CREATE DATABASE`` (quando a base de destino ainda não existe).
    postgres_maintenance_database: str = "postgres"
    postgres_auto_migrate: bool = True

    # CORS (origens separadas por vírgula; ex.: frontend Vite em localhost:5173)
    cors_origins: str = "http://localhost:5173"

    # Orquestrador — limites de loop, histórico, podagem de contexto
    orchestrator_max_tool_rounds: int = 24
    orchestrator_max_history_messages: int = 20
    orchestrator_max_message_age_seconds: float = 7200.0
    orchestrator_tool_result_preview_max: int = 500
    orchestrator_context_budget_safety_margin: int = 768
    orchestrator_chars_per_token_estimate: int = 3
    # Lista de agentes válidos (HTTP / handoff); separados por vírgula
    orchestrator_agent_types: str = (
        "maestro,analise_os,clusterizacao,visualizador,agregador,projecoes,"
        "verificador,compositor_layout"
    )
    # UUID usado como chave de cache do glossário quando não há session_id PostgreSQL
    orchestrator_glossary_cache_anonymous_uuid: str = "00000000-0000-0000-0000-000000000001"
    # Modelo OpenAI por agente (vazio = usar ``openai_model``)
    orchestrator_model_maestro: str = ""
    orchestrator_model_analise_os: str = ""
    orchestrator_model_clusterizacao: str = ""
    orchestrator_model_visualizador: str = ""
    orchestrator_model_agregador: str = ""
    orchestrator_model_projecoes: str = ""
    orchestrator_model_verificador: str = ""
    orchestrator_model_compositor_layout: str = ""

    # Glossário dinâmico (MySQL) fundido no system junto ao SKILL
    entity_glossary_enabled: bool = True
    # Nome da ferramenta MCP do glossário (deve coincidir com o servidor MCP)
    entity_glossary_mcp_tool: str = "get_entity_glossary_markdown"
    entity_glossary_max_chars: int = 24_000
    entity_glossary_on_handoff: bool = True
    # Pessoas no glossário: JOIN funcionario_cargos + cargos.funcionario_tipo_id (ver entity_glossary.py).
    entity_glossary_include_demais_registos: bool = True
    # Fragmentos SQL opcionais (começar por espaço + AND …, ou vazio). Vazio = sem filtro extra.
    # Ex.: ENTITY_GLOSSARY_SQL_FUN_EXTRA=" AND fun.ativo = 1 AND fun.deleted_at IS NULL"
    entity_glossary_sql_fun_extra: str = ""
    entity_glossary_sql_concessionarias_extra: str = ""
    entity_glossary_sql_servicos_extra: str = ""
    # Cache em RAM do markdown do glossário por session_id (evita MCP/MySQL a cada mensagem).
    entity_glossary_session_cache_enabled: bool = True
    entity_glossary_session_cache_max: int = 256

    # Teto de caracteres por mensagem tool para o LLM (~200k tokens estimados com CHARS_PER_TOKEN≈3).
    tool_message_content_max_chars: int = 600_000

    # Trace JSONL (orquestrador + cliente MCP); servidor MCP usa AGENT_TRACE_DIR e
    # AGENT_TRACE_MAX_FIELD_CHARS (sincronizado no arranque). 0 ou negativo = sem truncagem.
    agent_trace_enabled: bool = True
    agent_trace_dir: str = ""
    agent_trace_max_field_chars: int = 600_000

    # Memory prompts (master off; sub-flags só com master True)
    memory_prompts_enabled: bool = True
    memory_conversation_summary_enabled: bool = True
    memory_session_notes_enabled: bool = True
    memory_extraction_enabled: bool = True
    memory_consolidation_enabled: bool = True

    # Cache MCP em sessions.metadata (activo com sessão PostgreSQL)
    mcp_cache_entry_max_chars: int = 200_000
    mcp_cache_digest_max_chars: int = 12_000
    mcp_cache_digest_max_entries: int = 24
    mcp_cache_digest_max_chars_per_entry: int = 1800

    # Digest MCP — LLM editor (D16); fallback Python
    mcp_cache_digest_llm_enabled: bool = True
    mcp_cache_digest_llm_trigger: str = "when_base_too_long"
    mcp_cache_digest_llm_model: str = ""
    mcp_cache_digest_llm_timeout_seconds: float = 45.0
    mcp_cache_digest_llm_max_output_chars: int = 4000
    mcp_cache_digest_llm_min_chars_to_run: int = 2500
    mcp_cache_digest_llm_reuse_hash: bool = True

    # Frente 3 — verificador / compositor (pós-especialista)
    pipeline_verifier_enabled: bool = True
    pipeline_compositor_enabled: bool = True
    verification_depth: str = "smoke"

    # Observador (D18)
    observer_agent_enabled: bool = True
    observer_agent_model: str = ""
    observer_log_max_entries: int = 500
    observer_narratives_max: int = 50
    observer_narrative_max_chars: int = 8000

    @property
    def postgres_enabled(self) -> bool:
        return bool(self.postgres_host and self.postgres_user and self.postgres_database)

    @property
    def orchestrator_agent_types_frozenset(self) -> frozenset[str]:
        parts = [p.strip() for p in self.orchestrator_agent_types.split(",") if p.strip()]
        return frozenset(parts)

    @field_validator("orchestrator_glossary_cache_anonymous_uuid")
    @classmethod
    def _valid_anon_glossary_uuid(cls, v: str) -> str:
        UUID(v.strip())
        return v.strip()

    def orchestrator_glossary_cache_anonymous_key(self) -> UUID:
        return UUID(self.orchestrator_glossary_cache_anonymous_uuid)

    def resolve_orchestrator_model_for_agent(self, agent_type: str) -> str | None:
        """Modelo da API OpenAI para o agente; ``None`` se deve usar ``openai_model``."""
        m = {
            "maestro": self.orchestrator_model_maestro,
            "analise_os": self.orchestrator_model_analise_os,
            "clusterizacao": self.orchestrator_model_clusterizacao,
            "visualizador": self.orchestrator_model_visualizador,
            "agregador": self.orchestrator_model_agregador,
            "projecoes": self.orchestrator_model_projecoes,
            "verificador": self.orchestrator_model_verificador,
            "compositor_layout": self.orchestrator_model_compositor_layout,
        }
        raw = (m.get(agent_type) or "").strip()
        return raw if raw else None

    def effective_model_for_agent(self, agent_type: str) -> str:
        """Modelo final (override por agente ou ``openai_model`` ou fallback)."""
        o = self.resolve_orchestrator_model_for_agent(agent_type)
        if o:
            return o
        base = (self.openai_model or "").strip()
        return base if base else "gpt-4o-mini"


@lru_cache
def get_settings() -> Settings:
    return Settings()


def sync_mysql_env_from_settings(settings: Settings) -> None:
    """
    Escreve MYSQL_* em ``os.environ`` a partir do ``Settings`` (``.env`` / Pydantic).

    ``mcp_server.db`` usa ``os.environ``; o glossário corre no processo da API (uvicorn).
    Sem isto, valores herdados do shell (ex.: ``MYSQL_HOST=127.0.0.1``) podem prevalecer
    sobre o ``.env`` lido só pelo Pydantic — enquanto o subprocesso MCP arranca com outro ambiente.
    """
    import os

    host = (settings.mysql_host or "localhost").strip() or "localhost"
    os.environ["MYSQL_HOST"] = host
    os.environ["MYSQL_PORT"] = str(int(settings.mysql_port or 3306))
    os.environ["MYSQL_USER"] = settings.mysql_user or ""
    os.environ["MYSQL_PASSWORD"] = settings.mysql_password or ""
    os.environ["MYSQL_DATABASE"] = settings.mysql_database or ""


def resolve_agent_trace_dir(settings: Settings) -> "Path | None":
    """Directório onde são gravados ``{run_id}_app.jsonl`` e ``{run_id}_server.jsonl``."""
    from pathlib import Path

    if not settings.agent_trace_enabled:
        return None
    raw = (settings.agent_trace_dir or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return Path(__file__).resolve().parent.parent / "logs" / "agent_trace"

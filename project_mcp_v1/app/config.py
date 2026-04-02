from functools import lru_cache

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

    # Glossário dinâmico (MySQL) fundido no system junto ao SKILL
    entity_glossary_enabled: bool = True
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

    # Trace JSONL (orquestrador + cliente MCP); servidor MCP usa AGENT_TRACE_DIR
    agent_trace_enabled: bool = True
    agent_trace_dir: str = ""
    agent_trace_max_field_chars: int = 200_000

    @property
    def postgres_enabled(self) -> bool:
        return bool(self.postgres_host and self.postgres_user and self.postgres_database)


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

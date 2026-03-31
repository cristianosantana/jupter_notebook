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
    postgres_auto_migrate: bool = True

    # Trace JSONL (orchestrador + cliente MCP); servidor MCP usa AGENT_TRACE_DIR
    agent_trace_enabled: bool = True
    agent_trace_dir: str = ""
    agent_trace_max_field_chars: int = 200_000

    @property
    def postgres_enabled(self) -> bool:
        return bool(self.postgres_host and self.postgres_user and self.postgres_database)


@lru_cache
def get_settings() -> Settings:
    return Settings()



def resolve_agent_trace_dir(settings: Settings) -> "Path | None":
    """Directório onde são gravados ``{run_id}_app.jsonl`` e ``{run_id}_server.jsonl``."""
    from pathlib import Path

    if not settings.agent_trace_enabled:
        return None
    raw = (settings.agent_trace_dir or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return Path(__file__).resolve().parent.parent / "logs" / "agent_trace"

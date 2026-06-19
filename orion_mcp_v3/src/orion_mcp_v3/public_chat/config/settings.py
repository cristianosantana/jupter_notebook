"""Configuração isolada do Chat Público."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return default
    return int(raw)


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return default
    return float(raw)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class PublicChatSettings:
    enabled: bool = False
    use_presentation_snapshot: bool = False
    use_workspace: bool = False
    postgres_url: str = ""
    postgres_pool_min: int = 1
    postgres_pool_max: int = 10
    context_depth: int = 3
    intent_max_tokens: int = 512
    intent_min_confidence: float = 0.5
    llm_api_key: str = ""
    llm_base_url: str | None = None
    llm_model: str = "gpt-4o-mini"
    narrator_max_tokens: int = 1024
    selector_max_tokens: int = 256
    embedding_api_key: str = ""
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    ivfflat_probes: int = 10
    retrieval_limit: int = 5
    cache_ttl_days: int = 90
    pipeline_trace: bool = True
    pipeline_log_dir: str = "logs/public_chat"

    @property
    def pipeline_file_logging_enabled(self) -> bool:
        return self.pipeline_trace and bool(self.pipeline_log_dir.strip())

    @property
    def postgres_enabled(self) -> bool:
        return bool(self.postgres_url.strip())

    @property
    def llm_enabled(self) -> bool:
        return bool(self.llm_api_key.strip())

    @property
    def embedding_enabled(self) -> bool:
        return bool(self.effective_embedding_api_key.strip())

    @property
    def effective_embedding_api_key(self) -> str:
        return (self.embedding_api_key or self.llm_api_key).strip()

    @property
    def runtime_ready(self) -> bool:
        return (
            self.enabled
            and self.postgres_enabled
            and self.llm_enabled
            and self.embedding_enabled
        )

    @classmethod
    def from_env(cls, *, env_file: Path | None = None) -> PublicChatSettings:
        if env_file is not None and env_file.is_file():
            _load_dotenv(env_file)
        url = (
            os.environ.get("PUBLIC_CHAT_POSTGRES_URL")
            or os.environ.get("PUBLIC_CHAT_DATABASE_URL")
            or ""
        ).strip()
        llm_base = os.environ.get("PUBLIC_CHAT_LLM_BASE_URL")
        return cls(
            enabled=_env_bool("PUBLIC_CHAT_ENABLED", False),
            use_presentation_snapshot=_env_bool("PUBLIC_CHAT_USE_PRESENTATION_SNAPSHOT", False),
            use_workspace=_env_bool("PUBLIC_CHAT_USE_WORKSPACE", False),
            postgres_url=url,
            postgres_pool_min=_env_int("PUBLIC_CHAT_POSTGRES_POOL_MIN", 1),
            postgres_pool_max=_env_int("PUBLIC_CHAT_POSTGRES_POOL_MAX", 10),
            context_depth=_env_int("PUBLIC_CHAT_CONTEXT_DEPTH", 3),
            intent_max_tokens=_env_int("PUBLIC_CHAT_INTENT_MAX_TOKENS", 512),
            intent_min_confidence=_env_float("PUBLIC_CHAT_INTENT_MIN_CONFIDENCE", 0.5),
            llm_api_key=(os.environ.get("PUBLIC_CHAT_LLM_API_KEY") or "").strip(),
            llm_base_url=llm_base.strip() if llm_base else None,
            llm_model=(os.environ.get("PUBLIC_CHAT_LLM_MODEL") or "gpt-4o-mini").strip(),
            narrator_max_tokens=_env_int("PUBLIC_CHAT_NARRATOR_MAX_TOKENS", 1024),
            selector_max_tokens=_env_int("PUBLIC_CHAT_SELECTOR_MAX_TOKENS", 256),
            embedding_api_key=(os.environ.get("PUBLIC_CHAT_EMBEDDING_API_KEY") or "").strip(),
            embedding_model=(
                os.environ.get("PUBLIC_CHAT_EMBEDDING_MODEL") or "text-embedding-3-small"
            ).strip(),
            embedding_dimensions=_env_int("PUBLIC_CHAT_EMBEDDING_DIMENSIONS", 1536),
            ivfflat_probes=_env_int("PUBLIC_CHAT_IVFFLAT_PROBES", 10),
            retrieval_limit=_env_int("PUBLIC_CHAT_RETRIEVAL_LIMIT", 5),
            cache_ttl_days=_env_int("PUBLIC_CHAT_CACHE_TTL_DAYS", 90),
            pipeline_trace=_env_bool("PUBLIC_CHAT_PIPELINE_TRACE", True),
            pipeline_log_dir=(
                os.environ.get("PUBLIC_CHAT_PIPELINE_LOG_DIR") or "logs/public_chat"
            ).strip(),
        )


def default_env_files() -> tuple[Path, ...]:
    module_root = Path(__file__).resolve().parents[1]
    project_root = module_root.parents[1]
    return (
        module_root / ".env",
        project_root / ".env",
    )


def load_settings() -> PublicChatSettings:
    for path in default_env_files():
        if path.is_file():
            return PublicChatSettings.from_env(env_file=path)
    return PublicChatSettings.from_env()


def _load_dotenv(path: Path) -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(path)

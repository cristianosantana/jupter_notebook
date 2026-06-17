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


@dataclass(frozen=True, slots=True)
class PublicChatSettings:
    postgres_url: str = ""
    postgres_pool_min: int = 1
    postgres_pool_max: int = 10
    context_depth: int = 3
    intent_max_tokens: int = 512
    intent_min_confidence: float = 0.5

    @property
    def postgres_enabled(self) -> bool:
        return bool(self.postgres_url.strip())

    @classmethod
    def from_env(cls, *, env_file: Path | None = None) -> PublicChatSettings:
        if env_file is not None and env_file.is_file():
            _load_dotenv(env_file)
        url = (
            os.environ.get("PUBLIC_CHAT_POSTGRES_URL")
            or os.environ.get("PUBLIC_CHAT_DATABASE_URL")
            or ""
        ).strip()
        return cls(
            postgres_url=url,
            postgres_pool_min=_env_int("PUBLIC_CHAT_POSTGRES_POOL_MIN", 1),
            postgres_pool_max=_env_int("PUBLIC_CHAT_POSTGRES_POOL_MAX", 10),
            context_depth=_env_int("PUBLIC_CHAT_CONTEXT_DEPTH", 3),
            intent_max_tokens=_env_int("PUBLIC_CHAT_INTENT_MAX_TOKENS", 512),
            intent_min_confidence=_env_float("PUBLIC_CHAT_INTENT_MIN_CONFIDENCE", 0.5),
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

# app/core/config.py — Settings a partir de variáveis de ambiente
import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional


@dataclass(frozen=True)
class Settings:
    """Configuração lida de env. Não logar valores sensíveis."""

    openai_api_key: str
    modelo_default: str
    mysql_host: str
    mysql_port: int
    mysql_database: str
    mysql_user: str
    mysql_password: str
    time_interval_agents: float
    skills_dir: str


@lru_cache
def get_settings() -> Settings:
    return Settings(
        openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
        modelo_default=os.environ.get("MODELO_DEFAULT", "gpt-5-mini"),
        mysql_host=os.environ.get("MYSQL_HOST", "localhost"),
        mysql_port=int(os.environ.get("MYSQL_PORT", "3306") or 3306),
        mysql_database=os.environ.get("MYSQL_DATABASE", ""),
        mysql_user=os.environ.get("MYSQL_USER", "root"),
        mysql_password=os.environ.get("MYSQL_PASSWORD", ""),
        time_interval_agents=float(os.environ.get("TIME_INTERVAL_AGENTS", "2") or "2"),
        skills_dir=os.environ.get("SKILLS_DIR", "mnt/skills"),
    )

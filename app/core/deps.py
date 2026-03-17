# app/core/deps.py — Injeção de dependências para FastAPI
from typing import List, Optional

from fastapi import Depends
from openai import OpenAI

from app.core.config import Settings, get_settings
from app.core.skills import load_skills, get_skill_by_id
from app.services.maestro_service import MaestroService


def get_config() -> Settings:
    return get_settings()


def get_openai_client(settings: Settings = Depends(get_config)) -> OpenAI:
    return OpenAI(api_key=settings.openai_api_key or None)


def get_maestro_service(
    settings: Settings = Depends(get_config),
    client: OpenAI = Depends(get_openai_client),
) -> MaestroService:
    """Retorna o MaestroService com client e config injetados."""
    return MaestroService(client=client, settings=settings)


def get_skills_list(settings: Optional[Settings] = None) -> List[dict]:
    """Retorna a lista de skills carregada do diretório configurado."""
    s = settings or get_settings()
    return load_skills(s.skills_dir)

# app.core — Configuração e dependências
from .config import get_settings, Settings
from .skills import load_skills, get_skill_by_id

__all__ = ["get_settings", "Settings", "load_skills", "get_skill_by_id"]

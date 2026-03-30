"""Aplicação principal."""
from app.config import get_settings
from app.orchestrator import ModularOrchestrator

__all__ = ["get_settings", "ModularOrchestrator"]
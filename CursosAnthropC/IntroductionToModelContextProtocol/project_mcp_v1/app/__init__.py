"""Aplicação principal."""
from app.config import get_settings
from app.orchestrator import AgentOrchestrator

__all__ = ["get_settings", "AgentOrchestrator"]
"""Provedores de IA."""

from ai_provider.base import ModelProvider
from ai_provider.openai_provider import OpenAIProvider

__all__ = ["ModelProvider", "OpenAIProvider"]

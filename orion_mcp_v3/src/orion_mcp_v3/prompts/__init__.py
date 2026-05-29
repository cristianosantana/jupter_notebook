"""Prompts centralizados do Orion."""

from orion_mcp_v3.prompts.loader import PromptRegistry, get_prompt_registry, load_prompt_registry
from orion_mcp_v3.prompts.schemas import PromptSpec

__all__ = [
    "PromptRegistry",
    "PromptSpec",
    "get_prompt_registry",
    "load_prompt_registry",
]

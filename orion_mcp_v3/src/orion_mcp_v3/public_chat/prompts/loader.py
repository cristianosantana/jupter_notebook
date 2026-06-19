"""Loader de prompts YAML do módulo public_chat."""

from __future__ import annotations

from functools import lru_cache
from importlib import resources
from typing import Iterable

import yaml

from orion_mcp_v3.public_chat.prompts.schemas import PromptSpec


class PublicChatPromptRegistry:
    def __init__(self, specs: Iterable[PromptSpec]) -> None:
        self._specs = {spec.id: spec for spec in specs}

    def get(self, prompt_id: str) -> PromptSpec:
        try:
            return self._specs[prompt_id]
        except KeyError as exc:
            raise KeyError(f"prompt {prompt_id!r} not found") from exc

    def get_text(self, prompt_id: str) -> str:
        return self.get(prompt_id).system


def load_public_chat_prompt_registry() -> PublicChatPromptRegistry:
    root = resources.files("orion_mcp_v3.public_chat.prompts")
    registry_file = root.joinpath("registry.yaml")
    registry_raw = yaml.safe_load(registry_file.read_text(encoding="utf-8"))
    if not isinstance(registry_raw, dict):
        raise ValueError("public_chat prompt registry.yaml must contain a mapping")
    entries = registry_raw.get("prompts")
    if not isinstance(entries, list) or not entries:
        raise ValueError("public_chat prompt registry.yaml requires a non-empty prompts list")

    specs: list[PromptSpec] = []
    for filename in entries:
        path = root.joinpath(str(filename))
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(f"prompt file {filename!r} must contain a mapping")
        specs.append(PromptSpec.from_mapping(raw))
    return PublicChatPromptRegistry(specs)


@lru_cache(maxsize=1)
def get_public_chat_prompt_registry() -> PublicChatPromptRegistry:
    return load_public_chat_prompt_registry()

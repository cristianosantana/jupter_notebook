"""Loader centralizado de prompts YAML."""

from __future__ import annotations

from functools import lru_cache
from importlib import resources
from typing import Iterable

import yaml

from orion_mcp_v3.prompts.schemas import PromptSpec


class PromptRegistry:
    """Registry imutável de prompts versionados."""

    def __init__(self, specs: Iterable[PromptSpec]) -> None:
        self._specs = {spec.id: spec for spec in specs}

    def get(self, prompt_id: str) -> PromptSpec:
        try:
            return self._specs[prompt_id]
        except KeyError as exc:
            raise KeyError(f"prompt {prompt_id!r} not found") from exc

    def get_text(self, prompt_id: str) -> str:
        return self.get(prompt_id).system

    def get_fragment(self, prompt_id: str, name: str) -> str:
        spec = self.get(prompt_id)
        try:
            return spec.fragments[name]
        except KeyError as exc:
            raise KeyError(f"fragment {name!r} not found in prompt {prompt_id!r}") from exc

    def all(self) -> tuple[PromptSpec, ...]:
        return tuple(self._specs[key] for key in sorted(self._specs))


def load_prompt_registry() -> PromptRegistry:
    root = resources.files("orion_mcp_v3.prompts")
    registry_file = root.joinpath("registry.yaml")
    registry_raw = yaml.safe_load(registry_file.read_text(encoding="utf-8"))
    if not isinstance(registry_raw, dict):
        raise ValueError("prompt registry.yaml must contain a mapping")
    entries = registry_raw.get("prompts")
    if not isinstance(entries, list) or not entries:
        raise ValueError("prompt registry.yaml requires a non-empty prompts list")

    specs: list[PromptSpec] = []
    for filename in entries:
        path = root.joinpath(str(filename))
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(f"prompt file {filename!r} must contain a mapping")
        specs.append(PromptSpec.from_mapping(raw))
    return PromptRegistry(specs)


@lru_cache(maxsize=1)
def get_prompt_registry() -> PromptRegistry:
    return load_prompt_registry()

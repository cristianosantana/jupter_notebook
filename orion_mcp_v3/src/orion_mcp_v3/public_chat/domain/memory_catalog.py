"""Catálogo de memórias por tema — mapeamento fact_key → theme_slug."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any, Mapping

import yaml

from orion_mcp_v3.memory.remissive_models import slugify_memory_label


@dataclass(frozen=True, slots=True)
class MemoryThemeEntry:
    theme_slug: str
    category_patterns: tuple[str, ...]
    fact_keys: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MemoryCatalog:
    themes: tuple[MemoryThemeEntry, ...]
    join_keys: tuple[str, ...]
    version: str = "v1"

    def themes_for_fact(self, fact_key: str) -> tuple[str, ...]:
        result: list[str] = []
        for theme in self.themes:
            if fact_key in theme.fact_keys:
                result.append(theme.theme_slug)
        return tuple(result)

    def theme_entry(self, theme_slug: str) -> MemoryThemeEntry | None:
        for theme in self.themes:
            if theme.theme_slug == theme_slug:
                return theme
        return None

    def context_key_matches_theme(self, context_key: str, theme_slug: str) -> bool:
        """Associa hit a tema via segmento canónico do ``context_key`` (não usa ``category``)."""
        entry = self.theme_entry(theme_slug)
        if entry is None:
            return False
        key_theme = context_key_theme_slug(context_key)
        if not key_theme:
            return False
        key_norm = slugify_memory_label(key_theme)
        theme_norm = slugify_memory_label(theme_slug)
        if key_norm == theme_norm:
            return True
        for pattern in entry.category_patterns:
            pattern_slug = slugify_memory_label(pattern)
            if key_norm == pattern_slug or pattern_slug in key_norm:
                return True
        return False


def context_key_theme_slug(context_key: str) -> str | None:
    """Segmento 2 do ``context_key`` — slug canónico da categoria/tema na memória."""
    parts = [part.strip() for part in context_key.split(":") if part.strip()]
    if len(parts) < 2:
        return None
    return parts[1]


def _parse_theme(slug: str, raw: Mapping[str, Any]) -> MemoryThemeEntry:
    patterns = tuple(str(item) for item in (raw.get("category_patterns") or []))
    fact_keys = tuple(str(item) for item in (raw.get("fact_keys") or []))
    return MemoryThemeEntry(theme_slug=slug, category_patterns=patterns, fact_keys=fact_keys)


def load_memory_catalog(path: Path | None = None) -> MemoryCatalog:
    if path is not None:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    else:
        config_file = resources.files("orion_mcp_v3.public_chat.config").joinpath("memory_catalog.yaml")
        raw = yaml.safe_load(config_file.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("memory_catalog.yaml must be a mapping")
    version = str(raw.get("version") or "v1")
    themes_raw = raw.get("themes") or {}
    if not isinstance(themes_raw, dict):
        raise ValueError("memory_catalog.yaml themes must be a mapping")
    themes = tuple(_parse_theme(str(slug), item) for slug, item in themes_raw.items() if isinstance(item, dict))
    join_defaults = raw.get("join_defaults") or {}
    join_keys = tuple(str(item) for item in (join_defaults.get("join_keys") or ["period"]))
    return MemoryCatalog(themes=themes, join_keys=join_keys, version=version)


@lru_cache(maxsize=1)
def get_memory_catalog() -> MemoryCatalog:
    return load_memory_catalog()

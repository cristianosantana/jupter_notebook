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

    def category_matches_theme(
        self,
        category: str,
        theme_slug: str,
        *,
        context_key: str | None = None,
    ) -> bool:
        entry = self.theme_entry(theme_slug)
        if entry is None:
            return False
        theme_norm = slugify_memory_label(theme_slug)
        if context_key:
            key_category = _context_key_category_slug(context_key)
            if key_category and key_category == theme_norm:
                return True
        category_slug = slugify_memory_label(category)
        for pattern in entry.category_patterns:
            pattern_slug = slugify_memory_label(pattern)
            if category_slug == pattern_slug or pattern_slug in category_slug:
                return True
        return False


def _context_key_category_slug(context_key: str) -> str | None:
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

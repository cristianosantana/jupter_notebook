from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from orion_mcp_v2.config.settings import Settings

_BUNDLE = Path(__file__).resolve().parent / "reference_lookups.md"


@lru_cache(maxsize=16)
def _read_lookups_file(resolved_path: str) -> str:
    p = Path(resolved_path)
    return p.read_text(encoding="utf-8")


def resolve_reference_lookups_path(settings: "Settings") -> Path | None:
    if settings.reference_lookups_file is not None:
        p = settings.reference_lookups_file.expanduser().resolve()
        if p.is_file():
            return p
    return _BUNDLE if _BUNDLE.is_file() else None


def format_reference_lookups_block(settings: "Settings") -> str:
    """Texto markdown dos mapas ID→nome, truncado conforme settings."""
    if not settings.reference_lookups_enabled:
        return ""
    path = resolve_reference_lookups_path(settings)
    if path is None:
        return ""
    raw = _read_lookups_file(str(path))
    cap = settings.reference_lookups_max_chars
    if cap <= 0:
        return ""
    if len(raw) > cap:
        return (
            raw[:cap]
            + "\n\n… [truncado: aumentar ORION_V2_REFERENCE_LOOKUPS_MAX_CHARS ou usar ficheiro menor]"
        )
    return raw


def append_reference_lookups_to_system(system_prompt: str, settings: "Settings") -> str:
    block = format_reference_lookups_block(settings)
    if not block:
        return system_prompt
    return system_prompt.rstrip() + "\n\n" + block

"""Contratos para prompts versionados em YAML."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class PromptSpec:
    """Prompt carregado do diretório central de prompts."""

    id: str
    version: int
    purpose: str
    locale: str = "pt-BR"
    owner: str = ""
    system: str = ""
    fragments: Mapping[str, str] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "PromptSpec":
        prompt_id = str(raw.get("id") or "").strip()
        purpose = str(raw.get("purpose") or "").strip()
        if not prompt_id:
            raise ValueError("prompt id is required")
        if not purpose:
            raise ValueError(f"prompt {prompt_id!r} purpose is required")
        try:
            version = int(raw.get("version") or 0)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"prompt {prompt_id!r} version must be an integer") from exc
        if version < 1:
            raise ValueError(f"prompt {prompt_id!r} version must be >= 1")

        system = str(raw.get("system") or "").strip()
        fragments_raw = raw.get("fragments")
        fragments: dict[str, str] = {}
        if isinstance(fragments_raw, Mapping):
            for key, value in fragments_raw.items():
                text = str(value or "").strip()
                if text:
                    fragments[str(key)] = text
        if not system and not fragments:
            raise ValueError(f"prompt {prompt_id!r} requires system or fragments")

        metadata_raw = raw.get("metadata")
        return cls(
            id=prompt_id,
            version=version,
            locale=str(raw.get("locale") or "pt-BR").strip() or "pt-BR",
            owner=str(raw.get("owner") or "").strip(),
            purpose=purpose,
            system=system,
            fragments=fragments,
            metadata=dict(metadata_raw) if isinstance(metadata_raw, Mapping) else {},
        )

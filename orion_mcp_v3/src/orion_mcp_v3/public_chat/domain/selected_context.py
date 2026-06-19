"""Modelos de contexto seleccionado para narração."""

from __future__ import annotations

from dataclasses import dataclass

from orion_mcp_v3.public_chat.domain.section_parser import DocumentSection


@dataclass(frozen=True, slots=True)
class SelectedContext:
    sections: tuple[DocumentSection, ...]
    selection_reason: str | None = None
    degraded: bool = False
    source_context_chars: int = 0
    selected_context_chars: int = 0

    @property
    def has_sections(self) -> bool:
        return bool(self.sections)

    def as_prompt_dict(self) -> dict[str, object]:
        return {
            "sections": [
                {
                    "id": section.id,
                    "title": section.title,
                    "body": section.body,
                    "context_key": section.context_key,
                }
                for section in self.sections
            ],
            "selection_reason": self.selection_reason,
            "degraded": self.degraded,
        }

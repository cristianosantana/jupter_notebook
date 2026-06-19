"""Helpers de teste para selector pass-through."""

from __future__ import annotations

from orion_mcp_v3.public_chat.domain.intent_contract import IntentContract
from orion_mcp_v3.public_chat.domain.section_parser import ParsedDocument
from orion_mcp_v3.public_chat.domain.selected_context import SelectedContext
from orion_mcp_v3.public_chat.infrastructure.context_selector import PublicContextSelector


class PassthroughContextSelector(PublicContextSelector):
    async def select(
        self,
        message: str,
        *,
        contract: IntentContract,
        documents: tuple[ParsedDocument, ...],
    ) -> SelectedContext:
        sections = tuple(section for document in documents for section in document.sections)
        if not sections:
            return SelectedContext(sections=(), selection_reason="empty", degraded=True)
        chars = sum(len(section.body) for section in sections)
        return SelectedContext(
            sections=sections,
            selection_reason="passthrough_test",
            degraded=False,
            source_context_chars=chars,
            selected_context_chars=chars,
        )

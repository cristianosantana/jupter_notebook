"""Orquestra scoping, parsing e selecção de contexto."""

from __future__ import annotations

import time

from orion_mcp_v3.public_chat.domain.intent_contract import IntentContract
from orion_mcp_v3.public_chat.domain.knowledge import ConhecimentoRecuperado
from orion_mcp_v3.public_chat.domain.knowledge_scoper import scope_knowledge
from orion_mcp_v3.public_chat.domain.section_parser import parse_documents
from orion_mcp_v3.public_chat.domain.selected_context import SelectedContext
from orion_mcp_v3.public_chat.infrastructure.context_selector import PublicContextSelector
from orion_mcp_v3.public_chat.infrastructure.pipeline_trace import log_public_chat_event


async def prepare_selected_context(
    message: str,
    *,
    contract: IntentContract,
    knowledge: ConhecimentoRecuperado,
    selector: PublicContextSelector,
) -> SelectedContext:
    t_scope = time.monotonic()
    before_count = len(knowledge.hits)
    scoped, scope_degraded = scope_knowledge(knowledge, period=contract.period)
    log_public_chat_event(
        etapa="knowledge.scope",
        fase="post",
        dados={
            "latency_ms": round((time.monotonic() - t_scope) * 1000.0, 2),
            "hit_count_before": before_count,
            "hit_count_after": len(scoped.hits),
            "scope_degraded": scope_degraded,
            "period": contract.period,
        },
    )

    t_parse = time.monotonic()
    documents = parse_documents(scoped.hits)
    section_count = sum(len(document.sections) for document in documents)
    log_public_chat_event(
        etapa="section.parse",
        fase="post",
        dados={
            "latency_ms": round((time.monotonic() - t_parse) * 1000.0, 2),
            "document_count": len(documents),
            "section_count": section_count,
        },
    )

    if not scoped.has_hits:
        return SelectedContext(
            sections=(),
            selection_reason="no_hits",
            degraded=True,
        )

    selected = await selector.select(message, contract=contract, documents=documents)
    if scope_degraded and not selected.degraded:
        return SelectedContext(
            sections=selected.sections,
            selection_reason=selected.selection_reason,
            degraded=True,
            source_context_chars=selected.source_context_chars,
            selected_context_chars=selected.selected_context_chars,
        )
    return selected

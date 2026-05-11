"""
Recuperação semântica híbrida (Fase 3.2): lexical + metadata + intent + filtros.

Suporta filtros por ``entity``, ``intent`` e ``time_window`` sobre o pool recente,
e produz blocos com score composto (embedding placeholder + lexical + intent + metadata).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from orion_mcp_v3.contracts.context_block import ContextBlock, ContextRole, ContextSource
from orion_mcp_v3.memory.blocks import _ROLE_MAP
from orion_mcp_v3.memory.repositories.conversation_state import (
    ConversationMessage,
    ConversationStateRepository,
)


def _tokens(s: str) -> set[str]:
    return {t for t in re.split(r"\W+", s.lower()) if len(t) >= 2}


@dataclass(frozen=True, slots=True)
class SemanticHit:
    """Score decomposto de um hit semântico."""

    lexical_score: float
    intent_score: float
    metadata_score: float
    recency_score: float
    composite: float


_INTENT_KEYWORDS: dict[str, set[str]] = {
    "analytical": {"faturamento", "vendas", "total", "média", "media", "revenue", "sales", "sum", "count"},
    "recall": {"lembro", "falamos", "dissemos", "mencionou", "remember", "said", "talked"},
    "monitoring": {"alerta", "subiu", "desceu", "anomalia", "alert", "spike", "drop"},
    "execution": {"executa", "roda", "run", "execute", "gera", "generate"},
    "comparative": {"comparar", "comparado", "versus", "compare", "vs"},
    "temporal": {"mês", "meses", "semana", "ontem", "hoje", "month", "week", "yesterday", "today"},
}


def _lexical_score(query_toks: set[str], doc_toks: set[str]) -> float:
    if not query_toks or not doc_toks:
        return 0.0
    inter = len(query_toks & doc_toks)
    return inter / max(1, len(query_toks))


def _intent_score(intent_type: str | None, doc_toks: set[str]) -> float:
    if not intent_type:
        return 0.5
    kws = _INTENT_KEYWORDS.get(intent_type, set())
    if not kws:
        return 0.5
    hits = len(kws & doc_toks)
    return min(1.0, 0.3 + 0.7 * (hits / max(1, len(kws))))


def _metadata_score(msg: ConversationMessage) -> float:
    base = 0.5
    if msg.role == "user":
        base += 0.2
    elif msg.role == "assistant":
        base += 0.1
    length_bonus = min(0.15, len(msg.content) / 2000.0)
    return min(1.0, base + length_bonus)


def _recency_score_from_time(msg: ConversationMessage, now: float, half_life: float = 3600.0) -> float:
    age = max(0.0, now - msg.created_at.timestamp())
    if half_life <= 0:
        return 1.0
    return float(0.5 ** (age / half_life))


def _matches_entity_filter(msg: ConversationMessage, entities: Sequence[str]) -> bool:
    if not entities:
        return True
    lower = msg.content.lower()
    return any(e.lower() in lower for e in entities)


def _matches_intent_filter(msg: ConversationMessage, intent_type: str | None) -> bool:
    if not intent_type:
        return True
    kws = _INTENT_KEYWORDS.get(intent_type, set())
    if not kws:
        return True
    doc_toks = _tokens(msg.content)
    return bool(kws & doc_toks)


def _matches_time_window(msg: ConversationMessage, time_window: timedelta | None) -> bool:
    if time_window is None:
        return True
    now = datetime.now(timezone.utc)
    return (now - msg.created_at) <= time_window


def _score_message(
    msg: ConversationMessage,
    *,
    query_toks: set[str],
    intent_type: str | None,
    now: float,
) -> SemanticHit:
    doc_toks = _tokens(msg.content)
    lex = _lexical_score(query_toks, doc_toks)
    intent = _intent_score(intent_type, doc_toks)
    meta = _metadata_score(msg)
    rec = _recency_score_from_time(msg, now)
    composite = 0.40 * lex + 0.22 * intent + 0.18 * meta + 0.20 * rec
    return SemanticHit(
        lexical_score=lex,
        intent_score=intent,
        metadata_score=meta,
        recency_score=rec,
        composite=composite,
    )


def _hit_to_block(msg: ConversationMessage, hit: SemanticHit) -> ContextBlock:
    role = _ROLE_MAP.get(msg.role, ContextRole.NEUTRAL)
    return ContextBlock(
        text=msg.content,
        role=role,
        source=ContextSource.MEMORY,
        block_id=f"msg:{msg.message_id}",
        metadata={
            "conversation_role": msg.role,
            "semantic_hit": {
                "lexical": round(hit.lexical_score, 4),
                "intent": round(hit.intent_score, 4),
                "metadata": round(hit.metadata_score, 4),
                "recency": round(hit.recency_score, 4),
                "composite": round(hit.composite, 4),
            },
            "retrieval": "semantic",
            "created_at": msg.created_at.timestamp(),
        },
        relevance_score=max(hit.composite, 0.55),
        recency_score=hit.recency_score,
        confidence=min(1.0, 0.5 + hit.lexical_score * 0.5),
    )


class SemanticRetriever:
    """
    Retrieval híbrido (Fase 3.2): lexical + intent + metadata + recência,
    com filtros opcionais por ``entity``, ``intent_type`` e ``time_window``.
    """

    def __init__(self, repository: ConversationStateRepository) -> None:
        self._repo = repository

    def retrieve(
        self,
        query: str,
        session_id: str,
        *,
        pool_limit: int = 80,
        top_k: int = 5,
        intent_type: str | None = None,
        entities: Sequence[str] = (),
        time_window: timedelta | None = None,
    ) -> list[ContextBlock]:
        pool = self._repo.get_recent(session_id, limit=pool_limit)
        if not pool or not query.strip():
            return []

        filtered: list[ConversationMessage] = []
        for m in pool:
            if not _matches_entity_filter(m, entities):
                continue
            if not _matches_intent_filter(m, intent_type):
                continue
            if not _matches_time_window(m, time_window):
                continue
            filtered.append(m)

        if not filtered:
            filtered = pool[-min(top_k, len(pool)):]

        qtoks = _tokens(query)
        import time as _time
        now = _time.time()

        scored: list[tuple[SemanticHit, ConversationMessage]] = []
        for m in filtered:
            hit = _score_message(m, query_toks=qtoks, intent_type=intent_type, now=now)
            scored.append((hit, m))

        scored.sort(key=lambda x: -x[0].composite)
        top = scored[:max(1, top_k)]
        return [_hit_to_block(msg, hit) for hit, msg in top]

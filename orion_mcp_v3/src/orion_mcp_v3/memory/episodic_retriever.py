"""
Recuperação episódica com score composto (Fase 3.1).

Cada mensagem do repositório recebe um score multidimensional:
``semantic_similarity × recency × intent_match × entity_overlap × importance``
e os melhores blocos são devolvidos como :class:`~ContextBlock`.
"""

from __future__ import annotations

import re
import time as _time
from collections.abc import Sequence
from dataclasses import dataclass

from orion_mcp_v3.contracts.context_block import ContextBlock, ContextRole, ContextSource
from orion_mcp_v3.memory.blocks import _ROLE_MAP
from orion_mcp_v3.memory.repositories.conversation_state import (
    ConversationMessage,
    ConversationStateRepository,
)


def _tokens(s: str) -> set[str]:
    return {t for t in re.split(r"\W+", s.lower()) if len(t) >= 2}


@dataclass(frozen=True, slots=True)
class EpisodicScore:
    """Componentes individuais do score episódico."""

    semantic_similarity: float
    recency: float
    intent_match: float
    entity_overlap: float
    importance: float

    @property
    def composite(self) -> float:
        return (
            0.30 * self.semantic_similarity
            + 0.25 * self.recency
            + 0.18 * self.intent_match
            + 0.15 * self.entity_overlap
            + 0.12 * self.importance
        )


_INTENT_KEYWORDS: dict[str, set[str]] = {
    "analytical": {"faturamento", "vendas", "total", "média", "media", "revenue", "sales", "sum", "count", "metric"},
    "recall": {"lembro", "falamos", "dissemos", "mencionou", "remember", "said", "talked"},
    "monitoring": {"alerta", "subiu", "desceu", "anomalia", "alert", "spike", "drop"},
    "execution": {"executa", "roda", "run", "execute", "gera", "generate"},
    "comparative": {"comparar", "comparado", "versus", "compare", "vs"},
    "temporal": {"mês", "meses", "semana", "ontem", "hoje", "month", "week", "yesterday", "today"},
}

_IMPORTANCE_ROLES: dict[str, float] = {
    "user": 0.85,
    "assistant": 0.65,
    "system": 0.50,
    "tool": 0.40,
}


def _semantic_similarity(query_toks: set[str], msg_toks: set[str]) -> float:
    if not query_toks or not msg_toks:
        return 0.0
    inter = len(query_toks & msg_toks)
    return inter / max(1, len(query_toks))


def _recency_score(index: int, total: int) -> float:
    """Score linear crescente: mensagens mais recentes recebem score mais alto."""
    if total <= 1:
        return 1.0
    return (index + 1) / total


def _intent_match(intent_type: str | None, msg_toks: set[str]) -> float:
    if not intent_type:
        return 0.5
    kws = _INTENT_KEYWORDS.get(intent_type, set())
    if not kws:
        return 0.5
    hits = len(kws & msg_toks)
    return min(1.0, 0.3 + 0.7 * (hits / max(1, len(kws))))


def _entity_overlap(entities: Sequence[str], msg_toks: set[str]) -> float:
    if not entities:
        return 0.5
    ent_toks = {t.lower() for e in entities for t in re.split(r"\W+", e) if len(t) >= 2}
    if not ent_toks:
        return 0.5
    hits = len(ent_toks & msg_toks)
    return min(1.0, hits / max(1, len(ent_toks)))


def _importance(msg: ConversationMessage) -> float:
    base = _IMPORTANCE_ROLES.get(msg.role, 0.5)
    length_bonus = min(0.15, len(msg.content) / 2000.0)
    return min(1.0, base + length_bonus)


def score_message(
    msg: ConversationMessage,
    *,
    query_toks: set[str],
    index: int,
    total: int,
    intent_type: str | None = None,
    entities: Sequence[str] = (),
) -> EpisodicScore:
    msg_toks = _tokens(msg.content)
    return EpisodicScore(
        semantic_similarity=_semantic_similarity(query_toks, msg_toks),
        recency=_recency_score(index, total),
        intent_match=_intent_match(intent_type, msg_toks),
        entity_overlap=_entity_overlap(entities, msg_toks),
        importance=_importance(msg),
    )


def _msg_to_block(msg: ConversationMessage, score: EpisodicScore) -> ContextBlock:
    role = _ROLE_MAP.get(msg.role, ContextRole.NEUTRAL)
    return ContextBlock(
        text=msg.content,
        role=role,
        source=ContextSource.MEMORY,
        block_id=f"msg:{msg.message_id}",
        metadata={
            "conversation_role": msg.role,
            "episodic_score": {
                "semantic_similarity": round(score.semantic_similarity, 4),
                "recency": round(score.recency, 4),
                "intent_match": round(score.intent_match, 4),
                "entity_overlap": round(score.entity_overlap, 4),
                "importance": round(score.importance, 4),
                "composite": round(score.composite, 4),
            },
            "retrieval": "episodic",
            "created_at": msg.created_at.timestamp(),
        },
        relevance_score=score.composite,
        recency_score=score.recency,
        confidence=min(1.0, 0.5 + score.semantic_similarity * 0.5),
    )


class EpisodicRetriever:
    """
    Score composto multi-dimensional: similarity × recency × intent_match × entity_overlap × importance.

    Compatível com a interface anterior (``retrieve(session_id, limit=...)``), mas aceita
    ``query``, ``intent_type`` e ``entities`` para scoring mais rico.
    """

    def __init__(self, repository: ConversationStateRepository) -> None:
        self._repo = repository

    def retrieve(
        self,
        session_id: str,
        *,
        limit: int = 50,
        query: str | None = None,
        intent_type: str | None = None,
        entities: Sequence[str] = (),
        pool_limit: int | None = None,
    ) -> list[ContextBlock]:
        pool_sz = pool_limit or max(limit * 3, 120)
        msgs = self._repo.get_recent(session_id, limit=pool_sz)
        if not msgs:
            return []

        qtoks = _tokens(query) if query else set()
        total = len(msgs)

        scored: list[tuple[EpisodicScore, ConversationMessage]] = []
        for i, msg in enumerate(msgs):
            es = score_message(
                msg,
                query_toks=qtoks,
                index=i,
                total=total,
                intent_type=intent_type,
                entities=entities,
            )
            scored.append((es, msg))

        scored.sort(key=lambda x: -x[0].composite)
        top = scored[:limit]
        return [_msg_to_block(msg, es) for es, msg in top]

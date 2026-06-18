"""Orquestração de retrieval remissivo."""

from __future__ import annotations

import time

from orion_mcp_v3.public_chat.domain.knowledge import (
    AnswerPayload,
    ConhecimentoRecuperado,
)
from orion_mcp_v3.public_chat.infrastructure.pipeline_snapshots import (
    log_memory_accessed,
    snapshot_answer_payload,
)
from orion_mcp_v3.public_chat.infrastructure.pipeline_trace import log_public_chat_event, preview_message
from orion_mcp_v3.public_chat.infrastructure.remissive_reader import PublicRemissiveReader


class RemissiveRetriever:
    def __init__(self, reader: PublicRemissiveReader) -> None:
        self._reader = reader

    async def retrieve(self, query: str) -> ConhecimentoRecuperado:
        t0 = time.monotonic()
        log_public_chat_event(
            etapa="retriever.retrieve",
            fase="pre",
            dados=preview_message(query),
        )
        matches = await self._reader.search_origin_ids(query)
        if not matches:
            knowledge = ConhecimentoRecuperado()
            log_public_chat_event(
                etapa="retriever.retrieve",
                fase="post",
                dados={
                    "latency_ms": round((time.monotonic() - t0) * 1000.0, 2),
                    "match_count": 0,
                    "hit_count": 0,
                },
            )
            log_memory_accessed(
                source="vector_search+memory_curta",
                knowledge=knowledge,
                vector_matches=matches,
                reload_from_cache=False,
            )
            return knowledge
        origin_ids = [origin_id for origin_id, _ in matches]
        scores = {origin_id: score for origin_id, score in matches}
        hits = await self._reader.load_hits_by_origin_ids(origin_ids, scores=scores)
        knowledge = ConhecimentoRecuperado(hits=tuple(hits))
        log_public_chat_event(
            etapa="retriever.retrieve",
            fase="post",
            dados={
                "latency_ms": round((time.monotonic() - t0) * 1000.0, 2),
                "match_count": len(matches),
                "hit_count": len(hits),
            },
        )
        log_memory_accessed(
            source="vector_search+memory_curta",
            knowledge=knowledge,
            vector_matches=matches,
            reload_from_cache=False,
        )
        return knowledge

    async def reload_from_payload(self, payload: AnswerPayload | dict) -> ConhecimentoRecuperado:
        t0 = time.monotonic()
        if isinstance(payload, dict):
            answer = AnswerPayload.from_mapping(payload)
        else:
            answer = payload
        log_public_chat_event(
            etapa="retriever.reload_from_payload",
            fase="pre",
            dados={
                "reload_from_cache": True,
                "answer_payload": snapshot_answer_payload(answer),
            },
        )
        hits = await self._reader.load_hits_by_origin_ids(list(answer.knowledge_ids))
        essence = await self._reader.load_essence_by_themes(list(answer.essence_themes))
        knowledge = ConhecimentoRecuperado(hits=tuple(hits), essence=tuple(essence))
        log_public_chat_event(
            etapa="retriever.reload_from_payload",
            fase="post",
            dados={
                "latency_ms": round((time.monotonic() - t0) * 1000.0, 2),
                "hit_count": len(hits),
                "essence_count": len(essence),
            },
        )
        log_memory_accessed(
            source="cache_payload+memory_curta+memory_essence",
            knowledge=knowledge,
            reload_from_cache=True,
        )
        return knowledge

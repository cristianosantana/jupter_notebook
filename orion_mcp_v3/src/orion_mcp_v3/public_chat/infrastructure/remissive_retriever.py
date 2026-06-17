"""Orquestração de retrieval remissivo."""

from __future__ import annotations

from orion_mcp_v3.public_chat.domain.knowledge import (
    AnswerPayload,
    ConhecimentoRecuperado,
)
from orion_mcp_v3.public_chat.infrastructure.remissive_reader import PublicRemissiveReader


class RemissiveRetriever:
    def __init__(self, reader: PublicRemissiveReader) -> None:
        self._reader = reader

    async def retrieve(self, query: str) -> ConhecimentoRecuperado:
        matches = await self._reader.search_origin_ids(query)
        if not matches:
            return ConhecimentoRecuperado()
        origin_ids = [origin_id for origin_id, _ in matches]
        scores = {origin_id: score for origin_id, score in matches}
        hits = await self._reader.load_hits_by_origin_ids(origin_ids, scores=scores)
        return ConhecimentoRecuperado(hits=tuple(hits))

    async def reload_from_payload(self, payload: AnswerPayload | dict) -> ConhecimentoRecuperado:
        if isinstance(payload, dict):
            answer = AnswerPayload.from_mapping(payload)
        else:
            answer = payload
        hits = await self._reader.load_hits_by_origin_ids(list(answer.knowledge_ids))
        essence = await self._reader.load_essence_by_themes(list(answer.essence_themes))
        return ConhecimentoRecuperado(hits=tuple(hits), essence=tuple(essence))

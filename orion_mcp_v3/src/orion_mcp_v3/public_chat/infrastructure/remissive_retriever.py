"""Orquestração de retrieval remissivo."""

from __future__ import annotations

import time

from orion_mcp_v3.public_chat.domain.knowledge import (
    AnswerPayload,
    ConhecimentoRecuperado,
    KnowledgeHit,
)
from orion_mcp_v3.public_chat.domain.intent_contract import IntentContract
from orion_mcp_v3.public_chat.domain.memory_catalog import get_memory_catalog
from orion_mcp_v3.public_chat.domain.period_selection import contract_has_parcel_filter, periods_from_contract
from orion_mcp_v3.public_chat.domain.period_utils import period_in_context_key
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

    async def complete_period_evidence(
        self,
        *,
        knowledge: ConhecimentoRecuperado,
        contract: IntentContract,
    ) -> ConhecimentoRecuperado:
        periods = periods_from_contract(contract)
        if not periods:
            return knowledge

        required_keys = _target_key_metrics_keys(contract, knowledge)
        if not required_keys:
            return knowledge

        catalog_hits = await self._load_targeted_period_hits(periods, required_keys)
        if not catalog_hits:
            catalog_hits = await self._load_theme_period_hits()
        matching = tuple(
            hit
            for hit in catalog_hits
            if _hit_matches_any_period(hit, periods) and _hit_has_any_key(hit, required_keys)
        )
        merged = _merge_hits(knowledge.hits, matching)
        if len(merged) == len(knowledge.hits):
            return knowledge
        log_public_chat_event(
            etapa="retriever.complete_period_evidence",
            fase="post",
            dados={
                "periods": list(periods),
                "required_keys": list(required_keys),
                "hit_count_before": len(knowledge.hits),
                "hit_count_after": len(merged),
                "added_origin_ids": [
                    hit.origin_id for hit in merged if hit.origin_id not in {item.origin_id for item in knowledge.hits}
                ],
            },
        )
        return ConhecimentoRecuperado(hits=merged, essence=knowledge.essence)

    async def _load_targeted_period_hits(
        self,
        periods: tuple[str, ...],
        keys: tuple[str, ...],
    ) -> list[KnowledgeHit]:
        patterns = [
            f"%{_context_key_token_for_metric_key(key)}%{period}%"
            for period in periods
            for key in keys
        ]
        if hasattr(self._reader, "load_hits_by_context_key_patterns"):
            hits = await self._reader.load_hits_by_context_key_patterns(patterns)
            return hits if isinstance(hits, list) else []
        return []

    async def _load_theme_period_hits(self) -> list[KnowledgeHit]:
        catalog = get_memory_catalog()
        patterns: list[str] = []
        for theme in ("fechamento_gerencial", "fechamento_gerencial_mensal"):
            entry = catalog.theme_entry(theme)
            if entry is not None:
                patterns.extend(entry.category_patterns)
        if not patterns:
            return []
        return await self._reader.load_hits_by_theme_patterns(patterns)


def _key_metrics_keys_from_knowledge(knowledge: ConhecimentoRecuperado) -> tuple[str, ...]:
    keys: list[str] = []
    for hit in knowledge.hits:
        keys.extend(key for key in hit.key_metrics if not key.startswith("_"))
    return tuple(dict.fromkeys(keys))


def _target_key_metrics_keys(
    contract: IntentContract,
    knowledge: ConhecimentoRecuperado,
) -> tuple[str, ...]:
    metric = (contract.metric or "").lower()
    dimension = (contract.dimension or "").lower()
    operation = (contract.operation or "").lower()
    if contract_has_parcel_filter(contract) or dimension in {"parcelas", "parcelamento"}:
        return ("parcelamento_de_cartao",)
    if metric == "faturamento" and dimension in {"tipo_venda", "tipo_de_venda"}:
        return ("faturamento_por_tipo_de_venda",)
    if metric == "faturamento" and dimension in {"forma_pagamento", "tipo_pagamento", "tipo_de_pagamento"}:
        return ("faturamento_por_tipo_de_pagamento",)
    if metric == "faturamento" and not dimension and operation in {"comparison", "summary", ""}:
        return (
            "faturamento_por_tipo_de_venda",
            "faturamento_por_tipo_de_pagamento",
        )
    if metric in {"comissao", "comissão", "comissoes", "comissões"} and dimension in {
        "concessionaria",
        "concessionária",
    }:
        return ("faturamento_e_comissao_por_concessionaria",)
    if dimension in {"concessionaria", "concessionária"} and metric in {
        "comissao",
        "comissão",
        "comissoes",
        "comissões",
        "vendas",
        "",
    }:
        return ("faturamento_e_comissao_por_concessionaria",)
    return _key_metrics_keys_from_knowledge(knowledge)


def _context_key_token_for_metric_key(key: str) -> str:
    mapping = {
        "faturamento_por_tipo_de_venda": "faturamento_por_tipo_venda",
        "faturamento_por_tipo_de_pagamento": "faturamento_por_forma_pagamento",
        "parcelamento_de_cartao": "parcelamento_cartao",
        "faturamento_e_comissao_por_concessionaria": "comissao_por_concessionaria",
    }
    return mapping.get(key, key)


def _hit_matches_any_period(hit: KnowledgeHit, periods: tuple[str, ...]) -> bool:
    return any(period_in_context_key(hit.context_key, period) for period in periods)


def _hit_has_any_key(hit: KnowledgeHit, keys: tuple[str, ...]) -> bool:
    return any(key in hit.key_metrics for key in keys)


def _merge_hits(
    existing: tuple[KnowledgeHit, ...],
    extra: tuple[KnowledgeHit, ...],
) -> tuple[KnowledgeHit, ...]:
    merged: list[KnowledgeHit] = list(existing)
    seen = {hit.origin_id for hit in merged}
    for hit in extra:
        if hit.origin_id in seen:
            continue
        seen.add(hit.origin_id)
        merged.append(hit)
    return tuple(merged)

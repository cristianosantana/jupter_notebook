"""Snapshots estruturados para logs do pipeline (pergunta, memory_*, cache, resposta)."""

from __future__ import annotations

from typing import Any

from orion_mcp_v3.public_chat.domain.intent_contract import IntentContract
from orion_mcp_v3.public_chat.domain.knowledge import (
    AnswerPayload,
    ConhecimentoRecuperado,
    EssenceItem,
    KnowledgeHit,
)
from orion_mcp_v3.public_chat.infrastructure.pipeline_trace import log_public_chat_event, preview_message
from orion_mcp_v3.public_chat.infrastructure.response_store import CachedResolution


def _clip(text: str, *, max_len: int = 500) -> str:
    normalized = text.replace("\n", " ").strip()
    if len(normalized) <= max_len:
        return normalized
    return normalized[: max_len - 3] + "..."


def preview_answer(text: str, *, max_len: int = 800) -> dict[str, Any]:
    return {"answer_preview": _clip(text, max_len=max_len), "answer_chars": len(text)}


def snapshot_intent(contract: IntentContract) -> dict[str, Any]:
    return {
        "intent": contract.intent,
        "metric": contract.metric,
        "period": contract.period,
        "domain": contract.domain,
        "confidence": contract.confidence,
        "operation": contract.operation,
        "dimension": contract.dimension,
        "sort_direction": contract.sort_direction,
        "entity_filters": [item.as_mapping() for item in contract.entity_filters],
    }


def snapshot_vector_matches(
    matches: list[tuple[int, float | None]],
) -> list[dict[str, Any]]:
    return [
        {"origin_id": origin_id, "score": round(score, 6) if score is not None else None}
        for origin_id, score in matches
    ]


def snapshot_knowledge_hit(hit: KnowledgeHit) -> dict[str, Any]:
    return {
        "source": "memory_curta",
        "origin_id": hit.origin_id,
        "context_key": hit.context_key,
        "category": hit.category,
        "score": round(hit.score, 6) if hit.score is not None else None,
        "validated_answer_preview": _clip(hit.validated_answer, max_len=600),
        "validated_answer_chars": len(hit.validated_answer),
        "key_metrics": dict(hit.key_metrics),
    }


def snapshot_essence_item(item: EssenceItem) -> dict[str, Any]:
    return {
        "source": "memory_essence",
        "theme": item.theme,
        "observation_preview": _clip(item.observation or "", max_len=300) or None,
        "key_finding_preview": _clip(item.key_finding or "", max_len=300) or None,
        "recommendation_preview": _clip(item.recommendation or "", max_len=300) or None,
    }


def snapshot_knowledge(knowledge: ConhecimentoRecuperado) -> dict[str, Any]:
    return {
        "memory_curta_hits": [snapshot_knowledge_hit(hit) for hit in knowledge.hits],
        "memory_essence_items": [snapshot_essence_item(item) for item in knowledge.essence],
        "hit_count": len(knowledge.hits),
        "essence_count": len(knowledge.essence),
        "knowledge_ids": [hit.origin_id for hit in knowledge.hits],
        "context_keys": [hit.context_key for hit in knowledge.hits],
        "essence_themes": [item.theme for item in knowledge.essence],
    }


def snapshot_answer_payload(payload: AnswerPayload | dict[str, Any]) -> dict[str, Any]:
    if isinstance(payload, dict):
        answer = AnswerPayload.from_mapping(payload)
    else:
        answer = payload
    return {
        "context_keys": list(answer.context_keys),
        "knowledge_ids": list(answer.knowledge_ids),
        "essence_themes": list(answer.essence_themes),
    }


def snapshot_cache_resolution(cached: CachedResolution) -> dict[str, Any]:
    expires = cached.expires_at
    if hasattr(expires, "isoformat"):
        expires_at = expires.isoformat()
    else:
        expires_at = str(expires)
    return {
        "response_id": str(cached.id),
        "topic": cached.topic,
        "semantic_hash": cached.semantic_hash,
        "knowledge_fingerprint": cached.knowledge_fingerprint,
        "expires_at": expires_at,
        "answer_payload": snapshot_answer_payload(cached.answer_payload),
        "presentation_snapshot_chars": len(cached.presentation_snapshot or ""),
        "has_presentation_snapshot": bool(cached.presentation_snapshot),
    }


def log_memory_accessed(
    *,
    source: str,
    knowledge: ConhecimentoRecuperado,
    vector_matches: list[tuple[int, float | None]] | None = None,
    reload_from_cache: bool = False,
) -> None:
    dados: dict[str, Any] = {
        "source": source,
        "reload_from_cache": reload_from_cache,
        **snapshot_knowledge(knowledge),
    }
    if vector_matches is not None:
        dados["vector_matches"] = snapshot_vector_matches(vector_matches)
    log_public_chat_event(etapa="memory.accessed", fase="post", dados=dados)


def log_cache_resolution(
    *,
    cache_hit: bool,
    topic: str,
    semantic_hash: str,
    cached: CachedResolution | None = None,
) -> None:
    dados: dict[str, Any] = {
        "cache_hit": cache_hit,
        "lookup_key": {"topic": topic, "semantic_hash": semantic_hash},
    }
    if cached is not None:
        dados["cached_resolution"] = snapshot_cache_resolution(cached)
    log_public_chat_event(etapa="cache.resolution", fase="post", dados=dados)


def log_cache_stored(
    *,
    response_id: str,
    topic: str,
    semantic_hash: str,
    answer_payload: AnswerPayload,
    knowledge_fingerprint: str,
    is_repeat: bool,
    presentation_chars: int,
    stored_snapshot: bool,
) -> None:
    log_public_chat_event(
        etapa="cache.stored",
        fase="post",
        dados={
            "response_id": response_id,
            "lookup_key": {"topic": topic, "semantic_hash": semantic_hash},
            "answer_payload": snapshot_answer_payload(answer_payload),
            "knowledge_fingerprint": knowledge_fingerprint,
            "is_repeat": is_repeat,
            "presentation_chars": presentation_chars,
            "stored_presentation_snapshot": stored_snapshot,
        },
    )


def log_qa_turn_summary(
    *,
    pergunta: str,
    resposta: str,
    question_id: str,
    thread_id: str,
    response_id: str,
    cached: bool,
    cache_path: str,
    topic: str,
    semantic_hash: str,
    intent: str,
    confidence: float,
    is_repeat: bool,
    knowledge: ConhecimentoRecuperado | None = None,
    answer_payload: AnswerPayload | None = None,
    cache_resolution: CachedResolution | None = None,
    fingerprint_stale: bool = False,
    used_presentation_snapshot: bool = False,
    cache_stored: bool | None = None,
) -> None:
    """Evento consolidado pergunta → fontes memory_* / cache → resposta."""
    dados: dict[str, Any] = {
        "pergunta": preview_message(pergunta),
        "resposta": preview_answer(resposta),
        "question_id": question_id,
        "thread_id": thread_id,
        "response_id": response_id,
        "intent": intent,
        "confidence": confidence,
        "topic": topic,
        "semantic_hash": semantic_hash,
        "cache": {
            "path": cache_path,
            "hit": cached,
            "is_repeat": is_repeat,
            "fingerprint_stale": fingerprint_stale,
            "used_presentation_snapshot": used_presentation_snapshot,
        },
    }
    if cache_stored is not None:
        dados["cache"]["stored"] = cache_stored
    if knowledge is not None:
        dados["memory"] = snapshot_knowledge(knowledge)
    if answer_payload is not None:
        dados["answer_payload"] = snapshot_answer_payload(answer_payload)
    if cache_resolution is not None:
        dados["cached_resolution"] = snapshot_cache_resolution(cache_resolution)
    log_public_chat_event(etapa="qa.turn_summary", fase="post", dados=dados)

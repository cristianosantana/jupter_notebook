"""
Parser do payload JSON retornado pelo LLM e enriquecimento com evidências.

Responsabilidades:
  - parse_distillation_payload: str → SupervisedMemoryBatch
  - enrich_knowledge_from_windows: substitui validated_answer pela evidência
    mais longa encontrada nas janelas da conversa para o mesmo período.
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from dataclasses import replace
from typing import Any, Sequence

from orion_mcp_v3.memory.remissive_models import (
    CompressionLogEntry,
    RemissiveConversationWindow,
    RemissiveEssenceItem,
    RemissiveKnowledgeItem,
    SupervisedMemoryBatch,
    build_context_key,
)
from orion_mcp_v3.public_chat.domain.key_metrics_contract import enrich_key_metrics

from distillery.catalog import resolve_dimension, resolve_metric_kind
from distillery.field_parsers import (
    coerce_state_string,
    compression_ratio,
    confidence,
    mapping,
    optional_str,
    optional_str_any,
    optional_text,
    required_str,
    required_str_any,
    string_tuple_any,
)
from distillery.schema_fingerprint import default_fingerprint_store

logger = logging.getLogger(__name__)

# Chaves aceitas para validated_answer (inglês e português)
_VALIDATED_ANSWER_KEYS = (
    "validated_answer",
    "conteudo_resposta_validada",
    "resposta_validada",
    "validated_response",
    "answer",
    "resposta",
    "conteudo_validado",
    "conteudo",
)

# Regexes para extração de ano-mês em context_key e texto livre
_PERIOD_RANGE_RX    = re.compile(r"(\d{4}-\d{2})-\d{2}\s+a\s+\d{4}-\d{2}-\d{2}", re.IGNORECASE)
_CONTEXT_RANGE_RX   = re.compile(r"(\d{4}-\d{2})-\d{2}-to-\d{4}-\d{2}-\d{2}")
_CONTEXT_YM_RX      = re.compile(r":(\d{4}-\d{2})(?:$|:)")
_MONTH_NAMES = {
    "janeiro": 1,
    "jan": 1,
    "fevereiro": 2,
    "fev": 2,
    "marco": 3,
    "março": 3,
    "mar": 3,
    "abril": 4,
    "abriu": 4,
    "abr": 4,
    "maio": 5,
    "mai": 5,
    "junho": 6,
    "jun": 6,
    "julho": 7,
    "jul": 7,
    "agosto": 8,
    "ago": 8,
    "setembro": 9,
    "set": 9,
    "outubro": 10,
    "out": 10,
    "novembro": 11,
    "nov": 11,
    "dezembro": 12,
    "dez": 12,
}


# ---------------------------------------------------------------------------
# Validação de item de knowledge
# ---------------------------------------------------------------------------

def _item_label(item: dict[str, Any]) -> str:
    return (
        item.get("context_key")
        or item.get("contexto_chave")
        or item.get("theme")
        or item.get("tema")
        or "<sem-identificador>"
    )


def _validate_knowledge_item(item: dict[str, Any], validated_answer: str) -> bool:
    label = _item_label(item)
    if len(validated_answer.strip()) < 50:
        logger.warning("Item com resposta validada curta ignorado: %s", label)
        return False
    if confidence(item) == "low":
        logger.warning("Item com baixa confiança ignorado: %s", label)
        return False
    return True


# ---------------------------------------------------------------------------
# Parse de item de knowledge
# ---------------------------------------------------------------------------

def _parse_knowledge_item(item: dict[str, Any]) -> RemissiveKnowledgeItem | None:
    validated_answer = optional_str_any(item, *_VALIDATED_ANSWER_KEYS)
    if validated_answer is None:
        return None
    if not _validate_knowledge_item(item, validated_answer):
        return None

    user_id  = optional_str(item, "user_id") or "sistema_background"
    category = optional_str_any(item, "category", "categoria") or "Geral"
    theme    = required_str_any(item, "theme", "tema")
    periodo  = optional_str_any(item, "periodo", "period")

    metric_kind = resolve_metric_kind(
        optional_str_any(item, "metric_kind", "metrica", "metric")
    )
    dimension = resolve_dimension(
        optional_str_any(item, "dimension", "dimensao", "dimensão"),
        theme=theme,
    )
    raw_metrics = mapping(item, "key_metrics")
    normalized_metrics = enrich_key_metrics(
        raw_metrics,
        metric_kind=metric_kind,
        dimension=dimension,
        theme=theme,
    )
    default_fingerprint_store().check_and_update(
        theme=theme,
        dimension=dimension,
        key_metrics=normalized_metrics,
    )

    return RemissiveKnowledgeItem(
        user_id=user_id,
        category=category,
        context_key=build_context_key(user_id, category, theme, periodo),
        validated_answer=validated_answer,
        recent_questions=string_tuple_any(item, "recent_questions", "perguntas_recentes"),
        key_metrics=normalized_metrics,
        index_questions=string_tuple_any(
            item, "index_questions", "variacoes_perguntas_indice"
        ),
        metric_kind=metric_kind,
        dimension=dimension,
    )


# ---------------------------------------------------------------------------
# Parse de compression_log
# ---------------------------------------------------------------------------

def _parse_compression_log(raw: Any) -> CompressionLogEntry | None:
    if raw is None:
        return None
    if isinstance(raw, list):
        raw = next((item for item in raw if isinstance(item, dict)), None)
        if raw is None:
            raise ValueError("Campo compression_log deve conter objeto JSON.")
    if not isinstance(raw, dict):
        raise ValueError("Campo compression_log deve ser objeto JSON.")

    return CompressionLogEntry(
        user_id=optional_str(raw, "user_id"),
        from_state=coerce_state_string(
            raw.get("from_state"), default="raw_windows_v2"
        ),
        to_state=coerce_state_string(
            raw.get("to_state"), default="memoria_remissiva_v2"
        ),
        messages_compressed=int(raw.get("messages_compressed", 0) or 0),
        compression_ratio=compression_ratio(raw),
        what_was_kept=optional_text(raw, "what_was_kept"),
        what_was_dropped=optional_text(raw, "what_was_dropped"),
    )


# ---------------------------------------------------------------------------
# Ponto de entrada do parser
# ---------------------------------------------------------------------------

def parse_distillation_payload(text: str) -> SupervisedMemoryBatch:
    """
    Converte o texto JSON retornado pelo LLM em SupervisedMemoryBatch.

    Levanta ValueError para JSON inválido ou campos obrigatórios ausentes.
    Itens de knowledge inválidos (resposta curta, confidence=low) são
    descartados com log de warning sem interromper o parse.
    """
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("Resposta do LLM deve ser JSON estrito.") from exc
    if not isinstance(raw, dict):
        raise ValueError("Resposta do LLM deve ser um objeto JSON.")

    knowledge_raw = raw.get("knowledge", raw.get("conhecimento_lote", []))
    essence_raw   = raw.get("essence", [])

    if not isinstance(knowledge_raw, list):
        raise ValueError("Campo knowledge deve ser lista.")
    if not isinstance(essence_raw, list):
        raise ValueError("Campo essence deve ser lista.")

    knowledge = tuple(
        item
        for raw_item in knowledge_raw
        if isinstance(raw_item, dict)
        for item in (_parse_knowledge_item(raw_item),)
        if item is not None
    )

    essence = tuple(
        RemissiveEssenceItem(
            user_id=required_str(item, "user_id"),
            theme=required_str(item, "theme"),
            observation=optional_text(item, "observation"),
            key_finding=optional_text(item, "key_finding"),
            recommendation=optional_text(item, "recommendation"),
            stable_metrics=mapping(item, "stable_metrics"),
            confidence=confidence(item),
        )
        for item in essence_raw
        if isinstance(item, dict)
    )

    return SupervisedMemoryBatch(
        knowledge=knowledge,
        essence=essence,
        compression_log=_parse_compression_log(raw.get("compression_log")),
    )


# ---------------------------------------------------------------------------
# Enriquecimento com evidências das janelas
# ---------------------------------------------------------------------------

def _year_month_from_context_key(context_key: str) -> str | None:
    m = _CONTEXT_RANGE_RX.search(context_key)
    if m:
        return m.group(1)
    m = _CONTEXT_YM_RX.search(context_key)
    return m.group(1) if m else None


def _year_month_from_text(text: str) -> str | None:
    m = _PERIOD_RANGE_RX.search(text)
    if m:
        return m.group(1)
    m = re.search(r"(\d{4}-\d{2})-\d{2}", text)
    if m:
        return m.group(1)
    m = re.search(r"\b(20\d{2})-(0[1-9]|1[0-2])\b", text)
    if m:
        return f"{m.group(1)}-{m.group(2)}"

    normalized = unicodedata.normalize("NFKD", text.lower())
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    year_match = re.search(r"\b(20\d{2})\b", normalized)
    if not year_match:
        return None
    for month_name, month in _MONTH_NAMES.items():
        normalized_month = unicodedata.normalize("NFKD", month_name.lower())
        normalized_month = "".join(
            char for char in normalized_month if not unicodedata.combining(char)
        )
        if re.search(rf"\b{re.escape(normalized_month)}\b", normalized):
            return f"{year_match.group(1)}-{month:02d}"
    return None


def _message_content(message: dict[str, Any]) -> str:
    content = message.get("content")
    return content.strip() if isinstance(content, str) else ""


def _assistant_messages(window: RemissiveConversationWindow) -> tuple[str, ...]:
    """indexed_turns primeiro (texto integral); deduplica por conteúdo."""
    parts: list[str] = []
    seen: set[str] = set()
    for source in (window.indexed_turns, window.messages):
        for message in source:
            if str(message.get("role", "")).strip().lower() != "assistant":
                continue
            text = _message_content(message)
            if text and text not in seen:
                seen.add(text)
                parts.append(text)
    return tuple(parts)


def _window_year_month(window: RemissiveConversationWindow) -> str | None:
    for source in (window.messages, window.indexed_turns):
        for message in source:
            if str(message.get("role", "")).strip().lower() != "user":
                continue
            period = _year_month_from_text(_message_content(message))
            if period:
                return period
    for source in (window.messages, window.indexed_turns):
        for message in source:
            period = _year_month_from_text(_message_content(message))
            if period:
                return period
    return None


def _best_evidence(
    item: RemissiveKnowledgeItem,
    windows: Sequence[RemissiveConversationWindow],
) -> str | None:
    """Retorna a mensagem de assistant mais longa do período do item."""
    target_month = _year_month_from_context_key(item.context_key)
    if not target_month:
        return None
    candidates: list[str] = []
    for window in windows:
        window_month = _window_year_month(window)
        for text in _assistant_messages(window):
            text_month = _year_month_from_text(text)
            if text_month == target_month or (text_month is None and window_month == target_month):
                candidates.append(text)
    return max(candidates, key=len) if candidates else None


def enrich_knowledge_from_windows(
    batch: SupervisedMemoryBatch,
    windows: Sequence[RemissiveConversationWindow],
) -> SupervisedMemoryBatch:
    """
    Substitui validated_answer pela evidência mais completa encontrada
    nas janelas da conversa para o mesmo período do item.

    Não altera itens cujo período não seja identificável no context_key
    ou quando a evidência encontrada for menor que 50 caracteres.
    """
    if not batch.knowledge or not windows:
        return batch

    enriched: list[RemissiveKnowledgeItem] = []
    for item in batch.knowledge:
        evidence = _best_evidence(item, windows)
        if evidence and len(evidence) >= 50:
            if evidence != item.validated_answer:
                logger.info(
                    "validated_answer substituido por evidencia da conversa: "
                    "context_key=%s chars=%s→%s",
                    item.context_key,
                    len(item.validated_answer),
                    len(evidence),
                )
            enriched.append(replace(item, validated_answer=evidence))
        else:
            enriched.append(item)

    return replace(batch, knowledge=tuple(enriched))

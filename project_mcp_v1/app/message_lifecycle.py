"""
Poda de histórico por **segmentos** de conversa (invariante OpenAI: não partir tool_calls → tool).

Inclui classificação legada (``classify_message_importance`` / ``prune_excess_messages``) para outros usos;
o orquestrador usa ``pop_first_segment`` + ``strip_leading_orphan_tools``.
"""

from __future__ import annotations

import enum
from typing import Any

# Conteúdo tool acima disto era tratado como “rico” na poda antiga por importância.
_TOOL_CONTENT_PROTECT_MIN_CHARS = 400


class MessageImportance(enum.IntEnum):
    """Maior = remover por último ao reduzir histórico."""

    EPHEMERAL = 1
    LOW = 2
    NORMAL = 3
    HIGH = 4
    CRITICAL = 5


def _role(m: dict[str, Any]) -> str:
    return str(m.get("role") or "").strip().lower()


def classify_message_importance(msg: dict[str, Any]) -> MessageImportance:
    if msg.get("_orch_anchor"):
        return MessageImportance.CRITICAL
    role = _role(msg)
    content = msg.get("content")
    text = content if isinstance(content, str) else ""
    if role == "tool":
        if len(text) >= _TOOL_CONTENT_PROTECT_MIN_CHARS:
            return MessageImportance.CRITICAL
        return MessageImportance.NORMAL
    if role == "user":
        return MessageImportance.HIGH
    if role == "assistant":
        return MessageImportance.LOW if len(text) < 80 else MessageImportance.NORMAL
    return MessageImportance.NORMAL


def prune_excess_messages(
    messages: list[dict[str, Any]],
    message_times: list[float],
    max_total: int,
) -> None:
    """
    Legado: reduz por importância por mensagem (pode partir cadeias tool).

    Preferir ``pop_first_segment`` a partir do orquestrador. Mantido para compatibilidade.
    """
    if len(messages) != len(message_times):
        message_times.clear()
        message_times.extend([0.0] * len(messages))
    max_total = max(1, int(max_total))
    while len(messages) > max_total:
        scored: list[tuple[int, MessageImportance, int]] = []
        for i, m in enumerate(messages):
            imp = classify_message_importance(m)
            scored.append((i, imp, len(str(m.get("content", "")))))
        removable = [t for t in scored if t[1] < MessageImportance.CRITICAL]
        if not removable:
            scored.sort(key=lambda x: (x[1], x[2], x[0]))
            idx = scored[0][0]
        else:
            removable.sort(key=lambda x: (x[1], x[0]))
            idx = removable[0][0]
        messages.pop(idx)
        message_times.pop(idx)


def strip_leading_orphan_tools(
    messages: list[dict[str, Any]],
    message_times: list[float],
) -> None:
    """Remove ``tool`` consecutivas no início sem ``assistant`` com ``tool_calls`` antes."""
    while messages and _role(messages[0]) == "tool":
        messages.pop(0)
        message_times.pop(0)


def _consume_reply_block(messages: list[dict[str, Any]], start: int) -> int:
    """
    Avança ``start`` até ao próximo ``user`` ou fim, consumindo cadeias
    ``assistant`` (+ ``tool`` opcionais) e blocos órfãos de ``tool``.
    """
    n = len(messages)
    j = start
    while j < n:
        rr = _role(messages[j])
        if rr == "user":
            break
        if rr == "assistant":
            j += 1
            while j < n and _role(messages[j]) == "tool":
                j += 1
        elif rr == "tool":
            while j < n and _role(messages[j]) == "tool":
                j += 1
        else:
            j += 1
    return j


def first_prunable_segment_len(messages: list[dict[str, Any]]) -> int:
    """
    Número de mensagens contíguas desde o índice 0 que formam o primeiro segmento removível.

    Devolve 0 se não for seguro remover (ex.: âncora no índice 0 ou lista vazia).
    """
    if not messages:
        return 0
    if messages[0].get("_orch_anchor"):
        return 0
    n = len(messages)
    i = 0
    while i < n and _role(messages[i]) == "tool":
        i += 1
    if i > 0:
        return i
    r0 = _role(messages[0])
    if r0 == "system":
        return 1
    if r0 == "user":
        end = _consume_reply_block(messages, 1)
        return max(1, end)
    if r0 == "assistant":
        return max(1, _consume_reply_block(messages, 0))
    return 1


def pop_first_segment(
    messages: list[dict[str, Any]],
    message_times: list[float],
) -> bool:
    """
    Remove o primeiro segmento do início. Devolve ``True`` se removeu algo.
    """
    if len(messages) != len(message_times):
        message_times.clear()
        message_times.extend([0.0] * len(messages))
    k = first_prunable_segment_len(messages)
    if k <= 0:
        return False
    del messages[:k]
    del message_times[:k]
    return True



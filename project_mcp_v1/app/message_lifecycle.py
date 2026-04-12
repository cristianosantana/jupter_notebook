"""
Classificação de importância e poda de histórico sem remover primeiro o que é crítico
para contexto semântico (tool com dados, âncoras do orquestrador).
"""

from __future__ import annotations

import enum
from typing import Any

# Conteúdo tool acima disto é tratado como “rico” — remover por último.
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
    Reduz ``messages`` para no máximo ``max_total`` entradas, removendo primeiro
    as mensagens de menor importância (nunca começando por CRITICAL se houver alternativa).
    Mantém ``message_times`` alinhado por índice.
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
        # Candidatos removíveis: não CRITICAL, ou se todos CRITICAL, remover o menos crítico por tamanho
        removable = [t for t in scored if t[1] < MessageImportance.CRITICAL]
        if not removable:
            # Tudo crítico — remover a de menor índice com menor tamanho (último recurso)
            scored.sort(key=lambda x: (x[1], x[2], x[0]))
            idx = scored[0][0]
        else:
            removable.sort(key=lambda x: (x[1], x[0]))
            idx = removable[0][0]
        messages.pop(idx)
        message_times.pop(idx)

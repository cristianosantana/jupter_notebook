"""
Normalização de mensagens antes de ``chat.completions.create``.

A API OpenAI exige que cada ``role=tool`` siga (directa ou indirectamente) um
``assistant`` com ``tool_calls`` não vazio; removemos ``tool`` órfãs e
``tool_calls`` vazios/malformados.
"""

from __future__ import annotations

from typing import Any


def _tool_calls_non_empty(tc: object) -> bool:
    if tc is None:
        return False
    if isinstance(tc, list):
        return len(tc) > 0
    return bool(tc)


def _may_append_tool(out: list[dict[str, Any]]) -> bool:
    """Há um ``assistant`` com ``tool_calls`` válidos antes deste bloco de ``tool``?"""
    j = len(out) - 1
    while j >= 0:
        r = str(out[j].get("role") or "").strip().lower()
        if r == "tool":
            j -= 1
            continue
        if r == "assistant" and _tool_calls_non_empty(out[j].get("tool_calls")):
            return True
        return False
    return False


def sanitize_openai_chat_messages(
    messages: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """
    Devolve uma nova lista segura para a API (cópias rasas por mensagem).

    - Remove chaves internas ``_orch*`` (defesa em profundidade).
    - Remove ``tool_calls`` vazio ou não-lista em ``assistant``.
    - Omite ``tool`` sem ``assistant`` com ``tool_calls`` válidos antes (inclui
      ``tool`` logo após ``user`` / ``system`` / ``assistant`` sem tools).
    """
    if not messages:
        return []
    out: list[dict[str, Any]] = []
    for raw in messages:
        m = {
            k: v
            for k, v in raw.items()
            if not (isinstance(k, str) and k.startswith("_orch"))
        }
        role = str(m.get("role") or "").strip().lower()
        if role == "assistant":
            mm = dict(m)
            tc = mm.get("tool_calls")
            if isinstance(tc, list) and len(tc) == 0:
                mm.pop("tool_calls", None)
            elif tc is not None and not isinstance(tc, list):
                mm.pop("tool_calls", None)
            out.append(mm)
        elif role == "tool":
            if not _may_append_tool(out):
                continue
            out.append(dict(m))
        else:
            out.append(m)
    return out

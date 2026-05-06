"""Truncagem de resultados de tool com JSON válido para o LLM."""

from __future__ import annotations

import json
from typing import Any


def safe_truncate_tool_content(
    text: str,
    max_chars: int,
    *,
    cache_key: str | None = None,
) -> str:
    """
    Se ``text`` exceder ``max_chars``, devolve um único JSON com ``_truncated`` e um
    resumo; caso o corpo original fosse JSON parseável, o resumo inclui prefixo do
    objecto serializado.
    """
    max_chars = max(256, int(max_chars))
    if len(text) <= max_chars:
        return text

    hint = (
        "Conteúdo truncado pelo orquestrador (tool_message_content_max_chars). "
        "Reduza limit/offset, use summarize=true onde aplicável, ou consulte o digest/cache MCP."
    )
    if cache_key:
        hint += f" cache_key_prefix={cache_key[:40]}"

    parsed: Any | None
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        parsed = None

    budget = max(64, max_chars - 220)
    if isinstance(parsed, (dict, list)):
        summary = json.dumps(parsed, ensure_ascii=False)[:budget] + "…"
    else:
        summary = text[:budget] + "…"

    payload: dict[str, Any] = {
        "_truncated": True,
        "original_chars": len(text),
        "summary": summary,
        "hint": hint,
    }
    out = json.dumps(payload, ensure_ascii=False)
    if len(out) <= max_chars:
        return out

    payload["summary"] = summary[: max(0, max_chars - 180)] + "…"
    out = json.dumps(payload, ensure_ascii=False)
    if len(out) <= max_chars:
        return out

    return json.dumps(
        {"_truncated": True, "hint": hint[: max(0, max_chars - 40)]},
        ensure_ascii=False,
    )[:max_chars]

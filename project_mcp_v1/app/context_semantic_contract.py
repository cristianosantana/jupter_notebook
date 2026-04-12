"""Contrato mínimo para detectar placeholder de índice vazio em ``context_retrieve_similar``."""

from __future__ import annotations

from typing import Any

# Deve coincidir com o texto em ``mcp_server/context_retrieval/tools.py``.
CONTEXT_RETRIEVE_EMPTY_INDEX_MARKER = "Índice de contexto ainda vazio"


def is_empty_index_placeholder(injected: str | None) -> bool:
    return bool(injected) and CONTEXT_RETRIEVE_EMPTY_INDEX_MARKER in str(injected)


def summarize_like_prefilter(like_report: Any) -> dict[str, Any]:
    modes: dict[str, int] = {"ilike": 0, "fallback": 0, "other": 0}
    if not isinstance(like_report, list):
        return {"modes": modes, "sessions_reported": 0}
    for row in like_report:
        if not isinstance(row, dict):
            continue
        m = str(row.get("mode") or "")
        if m == "ilike":
            modes["ilike"] += 1
        elif m == "fallback":
            modes["fallback"] += 1
        else:
            modes["other"] += 1
    return {"modes": modes, "sessions_reported": len(like_report)}


def build_host_retrieve_ok_detail(data: dict[str, Any], chars: int) -> dict[str, Any]:
    injected = data.get("injected_context")
    inj_s = str(injected) if injected is not None else ""
    like_summary = summarize_like_prefilter(data.get("like_prefilter"))
    return {
        "chars": chars,
        "sessions_count": len(data.get("sessions") or []),
        "messages_preview_count": len(data.get("messages_preview") or []),
        "index_placeholder": is_empty_index_placeholder(inj_s),
        "like_prefilter": like_summary,
    }

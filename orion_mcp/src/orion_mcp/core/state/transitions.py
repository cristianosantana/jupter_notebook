from __future__ import annotations

from orion_mcp.core.state.turn_hints import ChatTurnHints
from orion_mcp.core.state.models import State


def update_state(state: State, user_input: str, hints: ChatTurnHints | None = None) -> State:
    """
    Deterministic state updates from user text (no LLM).
    Returns an updated copy for predictability in tests and persistence.
    """
    state = state.model_copy(deep=True)
    text = (user_input or "").strip()
    lower = text.lower()

    if lower in ("tabela", "html", "lista") or lower.startswith("formato "):
        state.intent = "format_only"
    elif "por que" in lower or "por quê" in lower or " why " in f" {lower} ":
        state.intent = "why_question"
    elif "atualizar" in lower or "refresh" in lower:
        state.flags["force_refresh"] = True
        state.intent = "refresh_data"
    elif text:
        state.intent = "general"

    # Minimal entity extraction: quoted strings
    if '"' in text:
        parts = [p.strip() for p in text.split('"') if len(p.strip()) > 1]
        if parts:
            state.entities["quoted"] = parts[:3]

    if hints is not None:
        _apply_chat_turn_hints(state, hints)

    return state


def _apply_chat_turn_hints(state: State, hints: ChatTurnHints) -> None:
    """Flags de domínio one-shot por pedido HTTP (ver plano Chat SQL unificado)."""
    if hints.date_from is not None:
        df = str(hints.date_from).strip()
        if df:
            state.filters["date_from"] = df
        else:
            state.filters.pop("date_from", None)
    if hints.date_to is not None:
        dt = str(hints.date_to).strip()
        if dt:
            state.filters["date_to"] = dt
        else:
            state.filters.pop("date_to", None)
    qid = (hints.query_id or "").strip()
    if qid:
        state.flags["domain_query_id"] = qid
        extra: dict[str, object] = {}
        if hints.limit is not None:
            extra["limit"] = int(hints.limit)
        if hints.offset is not None:
            extra["offset"] = int(hints.offset)
        if hints.summarize is not None:
            extra["summarize"] = bool(hints.summarize)
        state.flags["domain_query_extra"] = extra
    else:
        state.flags.pop("domain_query_id", None)
        state.flags.pop("domain_query_extra", None)


"""
Estado de negócio versionado por turno (metadata da sessão).

Chave em ``session_metadata``: ``conversation_state_v1``.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

ComplexityLiteral = Literal["low", "high"]


class ConversationStateV1(BaseModel):
    """Modelo versionado; incrementar ``v`` em mudanças incompatíveis."""

    v: int = Field(default=1, ge=1)
    complexity: ComplexityLiteral = "low"
    last_user_chars: int = 0
    last_turn_flow_mode: str = ""
    llm_calls_budget_remaining: int | None = None
    intent: str | None = None
    data_summary: str | None = None

    def merge_from_metadata(self, raw: dict[str, Any] | None) -> None:
        if not raw or not isinstance(raw, dict):
            return
        if int(raw.get("v") or 0) != 1:
            return
        try:
            merged = ConversationStateV1.model_validate({**self.model_dump(), **raw})
        except Exception:
            return
        self.complexity = merged.complexity
        self.last_user_chars = merged.last_user_chars
        self.llm_calls_budget_remaining = merged.llm_calls_budget_remaining
        self.intent = merged.intent
        self.data_summary = merged.data_summary

    def dump_for_metadata(self) -> dict[str, Any]:
        d = self.model_dump()
        d["v"] = 1
        return d


def load_conversation_state(meta: dict[str, Any] | None) -> ConversationStateV1:
    st = ConversationStateV1()
    if meta is None:
        return st
    raw = meta.get("conversation_state_v1")
    if isinstance(raw, dict):
        st.merge_from_metadata(raw)
    return st


def save_conversation_state_to_metadata(
    meta: dict[str, Any] | None,
    state: ConversationStateV1,
) -> None:
    if meta is None:
        return
    meta["conversation_state_v1"] = state.dump_for_metadata()


def update_state_from_input(state: ConversationStateV1, user_input: str) -> None:
    """Heurística inicial; futuro: passo LLM curto sob flag."""
    t = (user_input or "").strip()
    state.last_user_chars = len(t)
    if len(t) > 500 or (t.count("\n") >= 3 and len(t) > 200):
        state.complexity = "high"
    else:
        state.complexity = "low"

"""Modelos de domínio do Chat Público."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from orion_mcp_v3.public_chat.domain.intent_contract import IntentContract


@dataclass(frozen=True, slots=True)
class AncestorTurn:
    question_id: UUID
    query_original: str
    intent_contract: IntentContract

    def as_prompt_dict(self) -> dict[str, object]:
        return {
            "question_id": str(self.question_id),
            "query_original": self.query_original,
            "intent_contract": self.intent_contract.as_mapping(),
        }


@dataclass(frozen=True, slots=True)
class PublicQuestion:
    id: UUID
    thread_id: UUID
    parent_question_id: UUID | None
    topic: str
    intent_contract: IntentContract
    semantic_hash: str
    query_original: str
    created_at: datetime

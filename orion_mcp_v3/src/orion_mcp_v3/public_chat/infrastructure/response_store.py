"""Persistência de perguntas e cadeia ancestral do Chat Público."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

import asyncpg

from orion_mcp_v3.public_chat.domain.errors import InvalidParentQuestionError
from orion_mcp_v3.public_chat.domain.intent_contract import IntentContract
from orion_mcp_v3.public_chat.domain.models import AncestorTurn, PublicQuestion

_INSERT_QUESTION = """
INSERT INTO "public"."public_chat_questions" (
    "thread_id",
    "parent_question_id",
    "topic",
    "intent_contract",
    "semantic_hash",
    "query_original"
)
VALUES ($1, $2, $3, $4::jsonb, $5, $6)
RETURNING "id", "thread_id", "parent_question_id", "topic", "intent_contract",
          "semantic_hash", "query_original", "created_at"
"""

_SET_ROOT_THREAD = """
UPDATE "public"."public_chat_questions"
SET "thread_id" = "id"
WHERE "id" = $1 AND "parent_question_id" IS NULL
RETURNING "thread_id"
"""

_SELECT_QUESTION = """
SELECT "id", "thread_id", "parent_question_id", "topic", "intent_contract",
       "semantic_hash", "query_original", "created_at"
FROM "public"."public_chat_questions"
WHERE "id" = $1
"""


class ResponseStore:
    """Store parcial da fase 1 — perguntas e cadeia ancestral."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def insert_question(
        self,
        *,
        query_original: str,
        topic: str,
        intent_contract: IntentContract,
        semantic_hash: str,
        parent_question_id: UUID | None = None,
    ) -> PublicQuestion:
        parent_row: asyncpg.Record | None = None
        thread_id: UUID
        if parent_question_id is not None:
            parent_row = await self._fetch_question(parent_question_id)
            if parent_row is None:
                raise InvalidParentQuestionError(str(parent_question_id))
            thread_id = parent_row["thread_id"]
        else:
            thread_id = uuid4()

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                _INSERT_QUESTION,
                thread_id,
                parent_question_id,
                topic,
                json.dumps(intent_contract.as_mapping(), ensure_ascii=False),
                semantic_hash,
                query_original,
            )
            if row is None:
                raise RuntimeError("failed to insert public_chat question")

            question_id = row["id"]
            if parent_question_id is None:
                thread_row = await conn.fetchrow(_SET_ROOT_THREAD, question_id)
                if thread_row is not None:
                    row = await conn.fetchrow(_SELECT_QUESTION, question_id)
                    if row is None:
                        raise RuntimeError("failed to reload root question")

        return _row_to_question(row)

    async def load_ancestor_chain(
        self,
        question_id: UUID,
        max_depth: int,
    ) -> list[AncestorTurn]:
        if max_depth <= 0:
            return []

        collected: list[AncestorTurn] = []
        current_id: UUID | None = question_id
        while current_id is not None:
            row = await self._fetch_question(current_id)
            if row is None:
                break
            collected.append(
                AncestorTurn(
                    question_id=row["id"],
                    query_original=row["query_original"],
                    intent_contract=_contract_from_json(row["intent_contract"]),
                )
            )
            current_id = row["parent_question_id"]

        collected.reverse()
        if len(collected) > max_depth:
            collected = collected[-max_depth:]
        return collected

    async def get_question(self, question_id: UUID) -> PublicQuestion | None:
        row = await self._fetch_question(question_id)
        if row is None:
            return None
        return _row_to_question(row)

    async def _fetch_question(self, question_id: UUID) -> asyncpg.Record | None:
        async with self._pool.acquire() as conn:
            return await conn.fetchrow(_SELECT_QUESTION, question_id)


def _contract_from_json(value: Any) -> IntentContract:
    if isinstance(value, str):
        data = json.loads(value)
    elif isinstance(value, dict):
        data = value
    else:
        data = {}
    return IntentContract.from_mapping(data)


def _row_to_question(row: asyncpg.Record) -> PublicQuestion:
    return PublicQuestion(
        id=row["id"],
        thread_id=row["thread_id"],
        parent_question_id=row["parent_question_id"],
        topic=row["topic"],
        intent_contract=_contract_from_json(row["intent_contract"]),
        semantic_hash=row["semantic_hash"],
        query_original=row["query_original"],
        created_at=row["created_at"],
    )

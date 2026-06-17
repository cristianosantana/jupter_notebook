"""Persistência de perguntas e cadeia ancestral do Chat Público."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

import asyncpg

from orion_mcp_v3.public_chat.domain.errors import InvalidParentQuestionError
from orion_mcp_v3.public_chat.domain.intent_contract import IntentContract
from orion_mcp_v3.public_chat.domain.knowledge import AnswerPayload
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

_FIND_RESOLUTION = """
SELECT "id", "topic", "semantic_hash", "answer_payload", "knowledge_fingerprint", "expires_at"
FROM "public"."public_chat_responses"
WHERE "topic" = $1
  AND "semantic_hash" = $2
  AND "expires_at" > now()
"""

_UPSERT_RESOLUTION = """
INSERT INTO "public"."public_chat_responses" (
    "topic",
    "semantic_hash",
    "answer_payload",
    "knowledge_fingerprint",
    "expires_at"
)
VALUES ($1, $2, $3::jsonb, $4, $5)
ON CONFLICT ("topic", "semantic_hash")
DO UPDATE SET
    "answer_payload" = EXCLUDED."answer_payload",
    "knowledge_fingerprint" = EXCLUDED."knowledge_fingerprint",
    "expires_at" = EXCLUDED."expires_at"
RETURNING "id"
"""

_LINK_QUESTION_RESPONSE = """
INSERT INTO "public"."public_chat_question_responses" (
    "question_id",
    "response_id",
    "is_repeat",
    "presentation_delivered"
)
VALUES ($1, $2, $3, $4)
ON CONFLICT ("question_id", "response_id")
DO UPDATE SET
    "is_repeat" = EXCLUDED."is_repeat",
    "presentation_delivered" = EXCLUDED."presentation_delivered",
    "linked_at" = now()
"""


@dataclass(frozen=True, slots=True)
class CachedResolution:
    id: UUID
    topic: str
    semantic_hash: str
    answer_payload: AnswerPayload
    knowledge_fingerprint: str
    expires_at: datetime


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

    async def find_resolution(self, topic: str, semantic_hash: str) -> CachedResolution | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(_FIND_RESOLUTION, topic, semantic_hash)
        if row is None:
            return None
        return _row_to_resolution(row)

    async def upsert_resolution(
        self,
        *,
        topic: str,
        semantic_hash: str,
        answer_payload: AnswerPayload | dict,
        knowledge_fingerprint: str,
        cache_ttl_days: int = 90,
    ) -> UUID:
        payload = (
            answer_payload.as_mapping()
            if isinstance(answer_payload, AnswerPayload)
            else answer_payload
        )
        expires_at = datetime.now(timezone.utc) + timedelta(days=max(1, cache_ttl_days))
        async with self._pool.acquire() as conn:
            response_id = await conn.fetchval(
                _UPSERT_RESOLUTION,
                topic,
                semantic_hash,
                json.dumps(payload, ensure_ascii=False),
                knowledge_fingerprint,
                expires_at,
            )
        if response_id is None:
            raise RuntimeError("failed to upsert public_chat resolution")
        return response_id

    async def link_question_response(
        self,
        *,
        question_id: UUID,
        response_id: UUID,
        is_repeat: bool,
        presentation_delivered: str,
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                _LINK_QUESTION_RESPONSE,
                question_id,
                response_id,
                is_repeat,
                presentation_delivered,
            )


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


def _row_to_resolution(row: asyncpg.Record) -> CachedResolution:
    payload_raw = row["answer_payload"]
    if isinstance(payload_raw, str):
        payload_data = json.loads(payload_raw)
    elif isinstance(payload_raw, dict):
        payload_data = payload_raw
    else:
        payload_data = {}
    return CachedResolution(
        id=row["id"],
        topic=row["topic"],
        semantic_hash=row["semantic_hash"],
        answer_payload=AnswerPayload.from_mapping(payload_data),
        knowledge_fingerprint=row["knowledge_fingerprint"],
        expires_at=row["expires_at"],
    )

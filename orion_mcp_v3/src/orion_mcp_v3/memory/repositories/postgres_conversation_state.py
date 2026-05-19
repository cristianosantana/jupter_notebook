"""
Persistência de mensagens em PostgreSQL (asyncpg), alinhada a ``conversation_state``.

Usa a tabela ``conversation_state`` (JSONB ``messages``). Se existir a coluna
``external_id`` (migração 003), IDs de sessão não-UUID da API preservam-se na
listagem; caso contrário usa-se apenas ``session_id`` UUID (uuid5 determinístico
para strings arbitrárias).
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

import asyncpg

from orion_mcp_v3.memory.repositories.conversation_state import ConversationMessage

_LOG = logging.getLogger(__name__)

_ORION_CONVERSATION_NS = uuid.UUID("018f3b2e-7c4a-7b3e-9f0a-2d8e1c4b5a60")


def resolve_session_row_keys(conversation_id: str) -> tuple[uuid.UUID, str | None]:
    """
    Devolve ``(session_id_pk, external_id)``.

    * UUID válido → ``(uuid, None)``.
    * Outro texto → ``(uuid5(texto), texto)`` para gravar em ``external_id`` quando existir.
    """
    raw = (conversation_id or "").strip() or "default"
    try:
        return uuid.UUID(raw), None
    except ValueError:
        return uuid.uuid5(_ORION_CONVERSATION_NS, raw), raw


def _parse_ts(value: object) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    if isinstance(value, str):
        s = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    return datetime.now(timezone.utc)


def _messages_to_entries(msgs: list[ConversationMessage]) -> list[dict[str, object]]:
    return [
        {
            "role": m.role,
            "content": m.content,
            "message_id": m.message_id,
            "created_at": m.created_at.isoformat(),
        }
        for m in msgs
    ]


def _raw_to_messages(raw: object, *, session_key: str) -> list[ConversationMessage]:
    if raw is None:
        return []
    if isinstance(raw, (memoryview, bytes)):
        raw = raw.tobytes().decode() if isinstance(raw, memoryview) else raw.decode()
    if isinstance(raw, str):
        data = json.loads(raw)
    else:
        data = raw
    if not isinstance(data, list):
        return []
    out: list[ConversationMessage] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        mid = int(item.get("message_id", 0))
        role = str(item.get("role", "user"))
        content = str(item.get("content", ""))
        created = _parse_ts(item.get("created_at"))
        out.append(
            ConversationMessage(
                session_id=session_key,
                role=role,
                content=content,
                message_id=mid,
                created_at=created,
            )
        )
    return out


def _is_missing_external_id(exc: BaseException) -> bool:
    if isinstance(exc, asyncpg.UndefinedColumnError):
        return "external_id" in str(exc)
    return False


class PostgresConversationStateRepository:
    """Repositório asyncpg sobre ``conversation_state.messages`` (JSONB)."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool
        self._legacy_no_external_id = False

    def _effective_keys(self, session_id: str) -> tuple[uuid.UUID, str | None]:
        sid, ext = resolve_session_row_keys(session_id)
        if self._legacy_no_external_id:
            return sid, None
        return sid, ext

    async def append_message(self, session_id: str, role: str, content: str) -> ConversationMessage:
        for attempt in range(4):
            try:
                return await self._append_message_tx(session_id, role, content)
            except asyncpg.UniqueViolationError:
                if attempt >= 3:
                    raise
                _LOG.debug("conversation_state insert race, retrying (%s)", attempt)
            except asyncpg.UndefinedColumnError as e:
                if not self._legacy_no_external_id and _is_missing_external_id(e):
                    _LOG.warning(
                        "PostgreSQL: coluna external_id ausente — usar migração 003 "
                        "para listar IDs de sessão não-UUID; modo legado activo."
                    )
                    self._legacy_no_external_id = True
                    continue
                raise

        raise RuntimeError("unreachable")

    async def _append_message_tx(self, session_id: str, role: str, content: str) -> ConversationMessage:
        now = datetime.now(timezone.utc)
        role_norm = role.strip().lower()
        key = session_id.strip() or "default"
        sid, ext = self._effective_keys(session_id)

        async with self._pool.acquire() as conn:
            async with conn.transaction():
                if self._legacy_no_external_id:
                    row = await conn.fetchrow(
                        """
                        SELECT session_id, messages
                        FROM conversation_state
                        WHERE session_id = $1::uuid
                        FOR UPDATE
                        """,
                        sid,
                    )
                else:
                    row = await conn.fetchrow(
                        """
                        SELECT session_id, messages
                        FROM conversation_state
                        WHERE session_id = $1::uuid
                           OR ($2::text IS NOT NULL AND external_id = $2::text)
                        FOR UPDATE
                        """,
                        sid,
                        ext,
                    )

                if row is None:
                    entry: dict[str, object] = {
                        "role": role_norm,
                        "content": content,
                        "message_id": 1,
                        "created_at": now.isoformat(),
                    }
                    if self._legacy_no_external_id:
                        await conn.execute(
                            """
                            INSERT INTO conversation_state (session_id, messages)
                            VALUES ($1::uuid, $2::jsonb)
                            """,
                            sid,
                            json.dumps([entry]),
                        )
                    else:
                        await conn.execute(
                            """
                            INSERT INTO conversation_state (session_id, messages, external_id)
                            VALUES ($1::uuid, $2::jsonb, $3)
                            """,
                            sid,
                            json.dumps([entry]),
                            ext,
                        )
                    return ConversationMessage(
                        session_id=key,
                        role=role_norm,
                        content=content,
                        message_id=1,
                        created_at=now,
                    )

                existing = _raw_to_messages(row["messages"], session_key=key)
                n = (existing[-1].message_id + 1) if existing else 1
                new_msg = ConversationMessage(
                    session_id=key,
                    role=role_norm,
                    content=content,
                    message_id=n,
                    created_at=now,
                )
                merged = _messages_to_entries(existing) + [
                    {
                        "role": role_norm,
                        "content": content,
                        "message_id": n,
                        "created_at": now.isoformat(),
                    }
                ]
                if self._legacy_no_external_id:
                    await conn.execute(
                        """
                        UPDATE conversation_state
                        SET messages = $1::jsonb
                        WHERE session_id = $2::uuid
                        """,
                        json.dumps(merged),
                        row["session_id"],
                    )
                else:
                    await conn.execute(
                        """
                        UPDATE conversation_state
                        SET messages = $1::jsonb,
                            external_id = COALESCE(conversation_state.external_id, $3::varchar)
                        WHERE session_id = $2::uuid
                        """,
                        json.dumps(merged),
                        row["session_id"],
                        ext,
                    )
                return new_msg

    async def get_recent(self, session_id: str, limit: int = 50) -> list[ConversationMessage]:
        key = session_id.strip() or "default"
        sid, ext = self._effective_keys(session_id)

        async def _fetch() -> object | None:
            async with self._pool.acquire() as conn:
                if self._legacy_no_external_id:
                    return await conn.fetchrow(
                        """
                        SELECT messages
                        FROM conversation_state
                        WHERE session_id = $1::uuid
                        """,
                        sid,
                    )
                return await conn.fetchrow(
                    """
                    SELECT messages
                    FROM conversation_state
                    WHERE session_id = $1::uuid
                       OR ($2::text IS NOT NULL AND external_id = $2::text)
                    """,
                    sid,
                    ext,
                )

        try:
            row = await _fetch()
        except asyncpg.UndefinedColumnError as e:
            if not self._legacy_no_external_id and _is_missing_external_id(e):
                self._legacy_no_external_id = True
                row = await _fetch()
            else:
                raise

        if row is None:
            return []
        msgs = _raw_to_messages(row["messages"], session_key=key)
        if limit <= 0:
            return []
        return msgs[-limit:]

    async def list_session_ids(self) -> list[str]:
        async def _fetch_rows() -> list:
            async with self._pool.acquire() as conn:
                if self._legacy_no_external_id:
                    return await conn.fetch(
                        """
                        SELECT session_id::text AS cid
                        FROM conversation_state
                        ORDER BY created_at DESC NULLS LAST
                        """
                    )
                return await conn.fetch(
                    """
                    SELECT COALESCE(external_id, session_id::text) AS cid
                    FROM conversation_state
                    ORDER BY created_at DESC NULLS LAST
                    """
                )

        try:
            rows = await _fetch_rows()
        except asyncpg.UndefinedColumnError as e:
            if not self._legacy_no_external_id and _is_missing_external_id(e):
                self._legacy_no_external_id = True
                rows = await _fetch_rows()
            else:
                raise

        return [str(r["cid"]) for r in rows if r["cid"]]

"""
Persistência PostgreSQL: utilizadores opcionais, sessões e mensagens (transcript de especialistas).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import UUID

import asyncpg

from app.config import Settings


def _jsonb_text(value: Any) -> str | None:
    """Valor passível de guardar em JSONB como texto JSON (asyncpg + ::jsonb)."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return json.dumps(value, ensure_ascii=False)


def _message_to_db_tuple(
    session_id: UUID,
    seq: int,
    msg: dict[str, Any],
) -> tuple[Any, ...]:
    role = msg.get("role") or "user"
    content = msg.get("content")
    if content is not None and not isinstance(content, str):
        content = json.dumps(content, ensure_ascii=False)
    tool_name = msg.get("name") if role == "tool" else None
    tool_call_id = msg.get("tool_call_id")
    tool_args = None
    tool_calls_raw = msg.get("tool_calls")
    tool_calls: str | None
    if tool_calls_raw is None:
        tool_calls = None
    elif isinstance(tool_calls_raw, str):
        tool_calls = tool_calls_raw
    else:
        tool_calls = json.dumps(tool_calls_raw, ensure_ascii=False)

    skip = {"role", "content", "tool_call_id", "tool_calls", "name"}
    rest = {k: v for k, v in msg.items() if k not in skip}
    extra: str | None = _jsonb_text(rest) if rest else None

    return (session_id, seq, role, content, tool_name, tool_call_id, tool_args, tool_calls, extra)


def _row_to_message(
    role: str,
    content: str | None,
    tool_name: str | None,
    tool_call_id: str | None,
    tool_args: Any,
    tool_calls: Any,
    extra: Any,
) -> dict[str, Any]:
    msg: dict[str, Any] = {"role": role}
    if content is not None:
        msg["content"] = content
    if tool_call_id:
        msg["tool_call_id"] = tool_call_id
    if tool_calls:
        msg["tool_calls"] = tool_calls if not isinstance(tool_calls, str) else json.loads(tool_calls)
    if role == "tool" and tool_name:
        msg["name"] = tool_name
    if tool_args:
        msg["tool_args"] = tool_args if not isinstance(tool_args, str) else json.loads(tool_args)
    if extra:
        data: Any = json.loads(extra) if isinstance(extra, str) else extra
        if isinstance(data, dict):
            msg.update(data)
    return msg


class SessionStore:
    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    @classmethod
    async def create(cls, settings: Settings) -> SessionStore:
        pool = await asyncpg.create_pool(
            host=settings.postgres_host,
            port=settings.postgres_port,
            user=settings.postgres_user,
            password=settings.postgres_password or None,
            database=settings.postgres_database,
            min_size=1,
            max_size=10,
        )
        return cls(pool)

    async def close(self) -> None:
        await self._pool.close()

    @staticmethod
    def migration_sql_path() -> Path:
        return (
            Path(__file__).resolve().parent.parent
            / "migrations"
            / "postgres"
            / "001_initial.sql"
        )

    async def run_migrations(self, settings: Settings) -> None:
        if not settings.postgres_auto_migrate:
            return
        path = self.migration_sql_path()
        if not path.is_file():
            return
        sql = path.read_text(encoding="utf-8")
        async with self._pool.acquire() as conn:
            for stmt in sql.split(";"):
                stmt = stmt.strip()
                if stmt:
                    await conn.execute(stmt)

    async def upsert_user(self, user_id: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO users (user_id, updated_at)
                VALUES ($1, NOW())
                ON CONFLICT (user_id) DO UPDATE SET updated_at = NOW()
                """,
                user_id,
            )

    async def create_session(
        self,
        session_id: UUID,
        user_id: str | None,
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO sessions (session_id, user_id, current_agent, status, last_active_at)
                VALUES ($1, $2, 'maestro', 'active', NOW())
                """,
                session_id,
                user_id,
            )

    async def get_session(self, session_id: UUID) -> asyncpg.Record | None:
        async with self._pool.acquire() as conn:
            return await conn.fetchrow(
                "SELECT * FROM sessions WHERE session_id = $1",
                session_id,
            )

    async def touch_session(self, session_id: UUID, current_agent: str | None = None) -> None:
        async with self._pool.acquire() as conn:
            if current_agent:
                await conn.execute(
                    """
                    UPDATE sessions SET last_active_at = NOW(), current_agent = $2
                    WHERE session_id = $1
                    """,
                    session_id,
                    current_agent,
                )
            else:
                await conn.execute(
                    "UPDATE sessions SET last_active_at = NOW() WHERE session_id = $1",
                    session_id,
                )

    async def load_messages(self, session_id: UUID) -> list[dict[str, Any]]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT role, content, tool_name, tool_call_id, tool_args, tool_calls, extra
                FROM conversation_messages
                WHERE session_id = $1
                ORDER BY seq ASC
                """,
                session_id,
            )
        out: list[dict[str, Any]] = []
        for r in rows:
            out.append(
                _row_to_message(
                    r["role"],
                    r["content"],
                    r["tool_name"],
                    r["tool_call_id"],
                    r["tool_args"],
                    r["tool_calls"],
                    r["extra"],
                )
            )
        return out

    async def replace_conversation_messages(
        self,
        session_id: UUID,
        messages: list[dict[str, Any]],
    ) -> None:
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "DELETE FROM conversation_messages WHERE session_id = $1",
                    session_id,
                )
                for seq, msg in enumerate(messages):
                    row = _message_to_db_tuple(session_id, seq, msg)
                    await conn.execute(
                        """
                        INSERT INTO conversation_messages (
                            session_id, seq, role, content, tool_name, tool_call_id,
                            tool_args, tool_calls, extra
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9::jsonb)
                        """,
                        row[0],
                        seq,
                        row[2],
                        row[3],
                        row[4],
                        row[5],
                        row[6],
                        row[7],
                        row[8],
                    )

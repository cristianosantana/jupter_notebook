"""
Persistência PostgreSQL: utilizadores opcionais, sessões e mensagens (transcript de especialistas).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from uuid import UUID

import asyncpg

from app.config import Settings

# Nome da base de destino (CREATE DATABASE): só identificadores PostgreSQL seguros.
_POSTGRES_DB_NAME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]*$")


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

    @staticmethod
    async def _ensure_database_exists(settings: Settings) -> None:
        """
        Se ``postgres_database`` ainda não existir, cria-a (ligação à base ``postgres``).

        Evita ``InvalidCatalogNameError`` no primeiro arranque local/Docker.
        """
        dbname = (settings.postgres_database or "").strip()
        if not _POSTGRES_DB_NAME_RE.fullmatch(dbname):
            raise ValueError(
                "postgres_database deve ser um identificador PostgreSQL simples "
                "(letra inicial, depois letras, dígitos ou _)."
            )
        maint = (settings.postgres_maintenance_database or "postgres").strip() or "postgres"
        if not _POSTGRES_DB_NAME_RE.fullmatch(maint):
            raise ValueError("postgres_maintenance_database inválido (mesmas regras que postgres_database).")
        conn = await asyncpg.connect(
            host=settings.postgres_host,
            port=settings.postgres_port,
            user=settings.postgres_user,
            password=settings.postgres_password or None,
            database=maint,
        )
        try:
            row = await conn.fetchrow(
                "SELECT 1 FROM pg_database WHERE datname = $1",
                dbname,
            )
            if row is None:
                try:
                    await conn.execute(f"CREATE DATABASE {dbname}")
                except asyncpg.PostgresError as ex:
                    # 42P04 = duplicate_database (corrida entre workers ou criação paralela)
                    if getattr(ex, "sqlstate", None) == "42P04":
                        pass
                    else:
                        raise
        finally:
            await conn.close()

    @classmethod
    async def create(cls, settings: Settings) -> SessionStore:
        await cls._ensure_database_exists(settings)
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

    async def list_sessions(
        self,
        *,
        user_id: str | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Lista sessões por ``last_active_at`` descendente (máx. 100)."""
        cap = min(max(limit, 1), 100)
        async with self._pool.acquire() as conn:
            if user_id:
                rows = await conn.fetch(
                    """
                    SELECT session_id, user_id, current_agent, status,
                           started_at, last_active_at
                    FROM sessions
                    WHERE user_id = $1 AND EXISTS (SELECT 1 FROM conversation_messages WHERE sessions.session_id = conversation_messages.session_id)
                    ORDER BY last_active_at DESC
                    LIMIT $2
                    """,
                    user_id,
                    cap,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT session_id, user_id, current_agent, status,
                           started_at, last_active_at
                    FROM sessions
                    WHERE EXISTS (SELECT 1 FROM conversation_messages WHERE sessions.session_id = conversation_messages.session_id)
                    ORDER BY last_active_at DESC
                    LIMIT $1
                    """,
                    cap,
                )
        out: list[dict[str, Any]] = []
        for r in rows:
            out.append(
                {
                    "session_id": str(r["session_id"]),
                    "user_id": r["user_id"],
                    "current_agent": r["current_agent"],
                    "status": r["status"],
                    "started_at": r["started_at"].isoformat() if r["started_at"] else None,
                    "last_active_at": r["last_active_at"].isoformat() if r["last_active_at"] else None,
                }
            )
        return out
    async def update_session_metadata(
        self,
        session_id: UUID,
        metadata: dict[str, Any],
    ) -> None:
        """Substitui ``sessions.metadata`` (JSONB) pelo dict fornecido."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE sessions SET metadata = $2::jsonb, last_active_at = NOW()
                WHERE session_id = $1
                """,
                session_id,
                json.dumps(metadata, ensure_ascii=False),
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

    async def merge_session_metadata(
        self,
        session_id: UUID,
        patch: dict[str, Any],
    ) -> None:
        """Funde chaves em ``sessions.metadata`` (JSONB)."""
        if not patch:
            return
        payload = json.dumps(patch, ensure_ascii=False, default=str)
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE sessions
                SET metadata = COALESCE(metadata, '{}'::jsonb) || $2::jsonb
                WHERE session_id = $1
                """,
                session_id,
                payload,
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

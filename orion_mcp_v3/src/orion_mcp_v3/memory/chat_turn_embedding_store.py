"""
Persistência em ``chat_turn_embeddings`` (pgvector) — indexação por turno de chat.
"""

from __future__ import annotations

import hashlib
import logging

import asyncpg
from asyncpg.exceptions import UndefinedColumnError, UndefinedTableError

from orion_mcp_v3.memory.repositories.conversation_state import ConversationMessage
from orion_mcp_v3.protocols.embedding import EmbeddingService
from orion_mcp_v3.providers.openai_embedding import OpenAIEmbeddingService

_LOG = logging.getLogger(__name__)

_INSERT_WITH_CONTENT = """
INSERT INTO chat_turn_embeddings (
    session_id, message_id, role, content_hash, content, embedding
)
VALUES ($1, $2, $3, $4, $5, $6::vector)
ON CONFLICT (message_id) DO NOTHING
"""

_INSERT_LEGACY = """
INSERT INTO chat_turn_embeddings (
    session_id, message_id, role, content_hash, embedding
)
VALUES ($1, $2, $3, $4, $5::vector)
ON CONFLICT (message_id) DO NOTHING
"""


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _message_key(session_id: str, message_id: int) -> str:
    return f"{session_id.strip()}:{message_id}"


def _inserted(status: str) -> bool:
    return status.strip() == "INSERT 0 1"


class ChatTurnEmbeddingStore:
    """Grava e consulta embeddings por sessão na tabela ``chat_turn_embeddings``."""

    def __init__(self, pool: asyncpg.Pool, embedding_service: EmbeddingService) -> None:
        self._pool = pool
        self._embed = embedding_service
        self._use_content_column: bool | None = None
        # Evita re-embed da mesma query no mesmo turno (ex.: index user + search).
        self._query_vector_cache: dict[str, tuple[str, list[float]]] = {}

    async def _insert_row(
        self,
        conn: asyncpg.Connection,
        *,
        sid: str,
        mid: str,
        role: str,
        chash: str,
        content: str,
        vec_lit: str,
    ) -> str:
        if self._use_content_column is not False:
            try:
                status = await conn.execute(
                    _INSERT_WITH_CONTENT,
                    sid,
                    mid,
                    role,
                    chash,
                    content,
                    vec_lit,
                )
                self._use_content_column = True
                return status
            except UndefinedColumnError:
                self._use_content_column = False
                _LOG.warning(
                    "Coluna chat_turn_embeddings.content em falta — "
                    "aplique a migração 008_chat_turn_embeddings_content.sql"
                )

        return await conn.execute(
            _INSERT_LEGACY,
            sid,
            mid,
            role,
            chash,
            vec_lit,
        )

    async def index_turn(self, session_id: str, msg: ConversationMessage) -> bool:
        """
        Gera embedding e faz INSERT (idempotente por ``message_id``).

        Devolve True se uma linha foi inserida, False se conteúdo vazio ou duplicado.
        """
        content = (msg.content or "").strip()
        if not content:
            return False

        sid = session_id.strip() or "default"
        mid = _message_key(sid, msg.message_id)
        chash = _content_hash(content)
        role = msg.role.strip().lower()

        try:
            vectors = await self._embed.embed([content])
        except Exception:
            _LOG.exception("embedding API falhou session=%s message_id=%s", sid, mid)
            raise

        if not vectors:
            _LOG.warning("embedding API devolveu lista vazia session=%s message_id=%s", sid, mid)
            return False

        vec_lit = OpenAIEmbeddingService.to_pgvector(vectors[0])
        self._query_vector_cache[sid] = (chash, vectors[0])

        try:
            async with self._pool.acquire() as conn:
                status = await self._insert_row(
                    conn,
                    sid=sid,
                    mid=mid,
                    role=role,
                    chash=chash,
                    content=content,
                    vec_lit=vec_lit,
                )
        except UndefinedTableError:
            _LOG.error(
                "Tabela chat_turn_embeddings não existe — execute scripts/apply_migrations.py"
            )
            raise

        inserted = _inserted(status)
        if inserted:
            _LOG.info("chat_turn_embeddings gravado session=%s message_id=%s", sid, mid)
        else:
            _LOG.debug("chat_turn_embeddings ignorado (duplicado) session=%s message_id=%s", sid, mid)
        return inserted

    async def _vector_literal_for_query(self, session_id: str, query: str) -> str | None:
        q = (query or "").strip()
        if not q:
            return None
        sid = session_id.strip() or "default"
        chash = _content_hash(q)
        cached = self._query_vector_cache.get(sid)
        if cached is not None and cached[0] == chash:
            return OpenAIEmbeddingService.to_pgvector(cached[1])
        vectors = await self._embed.embed([q])
        if not vectors:
            return None
        self._query_vector_cache[sid] = (chash, vectors[0])
        return OpenAIEmbeddingService.to_pgvector(vectors[0])

    async def search(
        self,
        session_id: str,
        query: str,
        *,
        top_k: int = 5,
        query_vector_literal: str | None = None,
    ) -> list[tuple[str, str, str, float]]:
        """
        Busca por similaridade coseno na sessão.

        Devolve lista de ``(message_id, role, content, similarity)``.
        """
        q = (query or "").strip()
        if not q and query_vector_literal is None:
            return []

        sid = session_id.strip() or "default"
        vec_lit = query_vector_literal
        if vec_lit is None:
            vec_lit = await self._vector_literal_for_query(sid, q)
        if vec_lit is None:
            return []
        limit = max(1, top_k)

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT message_id, role, content,
                       1 - (embedding <=> $1::vector) AS similarity
                FROM chat_turn_embeddings
                WHERE session_id = $2
                ORDER BY embedding <=> $1::vector
                LIMIT $3
                """,
                vec_lit,
                sid,
                limit,
            )

        return [
            (
                str(r["message_id"]),
                str(r["role"] or "user"),
                str(r["content"] or ""),
                float(r["similarity"]),
            )
            for r in rows
            if str(r.get("content") or "").strip()
        ]

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import asyncpg

from .vectors import json_vec_to_list


async def resolve_user_id_for_session(
    conn: asyncpg.Connection,
    session_id: UUID,
) -> str | None:
    row = await conn.fetchrow(
        "SELECT user_id FROM sessions WHERE session_id = $1",
        session_id,
    )
    if row is None:
        return None
    uid = row["user_id"]
    return str(uid) if uid is not None else None


async def list_peer_sessions_for_user(
    conn: asyncpg.Connection,
    user_id: str,
    *,
    limit: int,
) -> list[UUID]:
    rows = await conn.fetch(
        """
        SELECT s.session_id
        FROM sessions s
        WHERE s.user_id = $1
          AND EXISTS (SELECT 1 FROM conversation_messages m WHERE m.session_id = s.session_id)
        ORDER BY s.last_active_at DESC
        LIMIT $2
        """,
        user_id,
        limit,
    )
    return [r["session_id"] for r in rows]


async def list_peer_sessions_anonymous(
    conn: asyncpg.Connection,
    anchor: UUID,
    *,
    limit: int,
) -> list[UUID]:
    """Sessões sem user_id: só a própria âncora (evita vazamento)."""
    rows = await conn.fetch(
        """
        SELECT session_id FROM sessions
        WHERE session_id = $1
          AND user_id IS NULL
          AND EXISTS (SELECT 1 FROM conversation_messages m WHERE m.session_id = sessions.session_id)
        LIMIT $2
        """,
        anchor,
        limit,
    )
    return [r["session_id"] for r in rows]


async def fetch_recent_messages(
    conn: asyncpg.Connection,
    session_id: UUID,
    *,
    max_messages: int,
) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """
        SELECT id, role, COALESCE(content, '') AS content, created_at
        FROM conversation_messages
        WHERE session_id = $1
        ORDER BY seq DESC
        LIMIT $2
        """,
        session_id,
        max_messages,
    )
    out: list[dict[str, Any]] = []
    for r in reversed(rows):
        out.append(
            {
                "id": int(r["id"]),
                "role": r["role"],
                "content": r["content"],
                "created_at": r["created_at"],
            }
        )
    return out


async def load_session_embeddings_for_anchor(
    conn: asyncpg.Connection,
    anchor: UUID,
    user_id: str | None,
    *,
    model: str,
) -> list[dict[str, Any]]:
    if user_id is not None:
        return await load_session_embeddings_for_user(conn, user_id, model=model)
    row = await conn.fetchrow(
        """
        SELECT se.session_id, se.embedding, se.cluster_id, se.text_digest
        FROM session_embeddings se
        WHERE se.session_id = $1 AND se.embedding_model = $2
        """,
        anchor,
        model,
    )
    return [dict(row)] if row else []


async def load_session_embeddings_for_user(
    conn: asyncpg.Connection,
    user_id: str,
    *,
    model: str,
) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """
        SELECT se.session_id, se.embedding, se.cluster_id, se.text_digest
        FROM session_embeddings se
        INNER JOIN sessions s ON s.session_id = se.session_id
        WHERE s.user_id = $1 AND se.embedding_model = $2
        """,
        user_id,
        model,
    )
    return [dict(r) for r in rows]


async def upsert_session_embedding(
    conn: asyncpg.Connection,
    *,
    session_id: UUID,
    model: str,
    embedding: list[float],
    text_digest: str | None,
) -> None:
    emb_json = json.dumps(embedding, ensure_ascii=False)
    await conn.execute(
        """
        INSERT INTO session_embeddings (session_id, embedding_model, embedding, text_digest, updated_at)
        VALUES ($1, $2, $3::jsonb, $4, NOW())
        ON CONFLICT (session_id) DO UPDATE SET
            embedding_model = EXCLUDED.embedding_model,
            embedding = EXCLUDED.embedding,
            text_digest = EXCLUDED.text_digest,
            updated_at = NOW()
        """,
        session_id,
        model,
        emb_json,
        text_digest,
    )


async def fetch_message_embeddings(
    conn: asyncpg.Connection,
    message_ids: list[int],
    *,
    model: str,
) -> dict[int, list[float]]:
    """Vectores persistidos por ``message_id`` (tabela ``conversation_message_embeddings``)."""
    if not message_ids:
        return {}
    rows = await conn.fetch(
        """
        SELECT message_id, embedding
        FROM conversation_message_embeddings
        WHERE embedding_model = $1 AND message_id = ANY($2::bigint[])
        """,
        model,
        message_ids,
    )
    out: dict[int, list[float]] = {}
    for r in rows:
        out[int(r["message_id"])] = json_vec_to_list(r["embedding"])
    return out


async def upsert_message_embeddings_batch(
    conn: asyncpg.Connection,
    rows: list[tuple[int, UUID, str, list[float]]],
) -> int:
    """
    Grava embeddings por mensagem; só afecta linhas onde ``conversation_messages`` confirma o par
    ``(id, session_id)``.
    Devolve número de UPSERTs efectivos (RETURNING).
    """
    n = 0
    for mid, sid, model, vec in rows:
        emb_json = json.dumps(vec, ensure_ascii=False)
        rec = await conn.fetchrow(
            """
            INSERT INTO conversation_message_embeddings (message_id, session_id, embedding_model, embedding)
            SELECT m.id, m.session_id, $3::varchar(64), $4::jsonb
            FROM conversation_messages m
            WHERE m.id = $1::bigint AND m.session_id = $2::uuid
            ON CONFLICT (message_id, embedding_model) DO UPDATE SET
                embedding = EXCLUDED.embedding,
                session_id = EXCLUDED.session_id
            RETURNING message_id
            """,
            mid,
            sid,
            model,
            emb_json,
        )
        if rec:
            n += 1
    return n


async def update_session_cluster(
    conn: asyncpg.Connection,
    *,
    session_id: UUID,
    cluster_id: int | None,
    model_version: str,
) -> None:
    await conn.execute(
        """
        UPDATE session_embeddings
        SET cluster_id = $2, cluster_model_version = $3, updated_at = NOW()
        WHERE session_id = $1
        """,
        session_id,
        cluster_id,
        model_version,
    )


async def replace_kmeans_centroids(
    conn: asyncpg.Connection,
    *,
    model_version: str,
    n_clusters: int,
    centroids: list[list[float]],
    n_points: list[int],
) -> None:
    await conn.execute(
        "DELETE FROM kmeans_centroids WHERE model_version = $1",
        model_version,
    )
    for i, c in enumerate(centroids):
        np = n_points[i] if i < len(n_points) else 0
        await conn.execute(
            """
            INSERT INTO kmeans_centroids (model_version, n_clusters, cluster_id, centroid, n_points)
            VALUES ($1, $2, $3, $4::jsonb, $5)
            """,
            model_version,
            n_clusters,
            i,
            json.dumps(c, ensure_ascii=False),
            np,
        )


async def ilike_candidate_messages(
    conn: asyncpg.Connection,
    session_id: UUID,
    *,
    pattern: str,
    limit: int,
) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """
        SELECT id, role, COALESCE(content, '') AS content
        FROM conversation_messages
        WHERE session_id = $1 AND content ILIKE $2 ESCAPE '\\'
        ORDER BY created_at DESC
        LIMIT $3
        """,
        session_id,
        pattern,
        limit,
    )
    return [dict(r) for r in rows]

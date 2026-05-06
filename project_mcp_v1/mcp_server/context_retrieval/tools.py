"""
Tools MCP: context_embed_sessions, context_rebuild_kmeans, context_retrieve_similar.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any
from uuid import UUID

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from context_retrieval.batch_embed import run_embed_sessions_for_anchor_session
from context_retrieval.embedder import embed_texts, embed_texts_batched
from context_retrieval.like_pattern import question_to_ilike_pattern
from context_retrieval.message_embed import run_embed_messages_for_session
from context_retrieval.prefilter import load_messages_for_retrieve
from context_retrieval.clustering import fit_kmeans, silhouette_optional
from context_retrieval.pool import get_pg_pool
from context_retrieval.repository import (
    fetch_message_embeddings,
    ilike_candidate_messages,
    load_session_embeddings_for_anchor,
    replace_kmeans_centroids,
    resolve_user_id_for_session,
    update_session_cluster,
    upsert_message_embeddings_batch,
)
from context_retrieval.vectors import (
    cosine_similarity,
    json_vec_to_list,
    merge_message_vectors_for_retrieve,
)

from app.context_semantic_contract import (
    CONTEXT_RETRIEVE_EMPTY_INDEX_MARKER,
    summarize_like_prefilter,
)

_logger = logging.getLogger(__name__)


def _json_response(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


def register_context_retrieval_tools(mcp: FastMCP) -> None:
    @mcp.tool(
        name="context_embed_sessions",
        description=(
            "Indexação batch: gera **um embedding por sessão** (texto agregado das últimas mensagens) "
            "e grava em `session_embeddings`. Opcional **`anchor_query`**: agrega só mensagens que passam "
            "o pré-filtro ILIKE (alinhado ao runtime de `context_retrieve_similar`). "
            "Custo: chamadas OpenAI embeddings. Requer `session_id` na BD. "
            "Use após existir transcript em `conversation_messages`."
        ),
        annotations=ToolAnnotations(readOnlyHint=False),
    )
    async def context_embed_sessions(
        session_id: str,
        limit: int = 16,
        anchor_query: str | None = None,
    ) -> str:
        from app.config import get_settings

        st = get_settings()
        lim = max(1, min(int(limit), int(st.context_embed_sessions_limit_default * 4)))
        anchor = (anchor_query or "").strip()
        try:
            sid = UUID(session_id.strip())
        except ValueError:
            return _json_response({"ok": False, "error": "session_id inválido"})
        try:
            result = await run_embed_sessions_for_anchor_session(
                sid,
                limit=lim,
                anchor_query=anchor or None,
            )
        except Exception as e:
            _logger.exception("context_embed_sessions")
            return _json_response({"ok": False, "error": str(e)[:500]})
        return _json_response(result)

    @mcp.tool(
        name="context_embed_messages",
        description=(
            "Indexação por **mensagem**: gera embeddings OpenAI para mensagens recentes (ou filtradas por "
            "``anchor_query`` com ILIKE, como no retrieve) e grava em ``conversation_message_embeddings``. "
            "Reduz chamadas no ``context_retrieve_similar`` quando ``CONTEXT_MESSAGE_EMBEDDINGS_ENABLED=true``. "
            "Custo proporcional a mensagens em falta. Requer ``session_id`` existente na BD."
        ),
        annotations=ToolAnnotations(readOnlyHint=False),
    )
    async def context_embed_messages(
        session_id: str,
        limit: int = 48,
        anchor_query: str | None = None,
    ) -> str:
        try:
            sid = UUID(session_id.strip())
        except ValueError:
            return _json_response({"ok": False, "error": "session_id inválido"})
        lim = max(1, min(int(limit), 200))
        anchor = (anchor_query or "").strip() or None
        try:
            result = await run_embed_messages_for_session(
                sid,
                limit=lim,
                anchor_query=anchor,
            )
        except Exception as e:
            _logger.exception("context_embed_messages")
            return _json_response({"ok": False, "error": str(e)[:500]})
        return _json_response(result)

    @mcp.tool(
        name="context_rebuild_kmeans",
        description=(
            "Batch/admin: ajusta K-Means sobre os vectores em `session_embeddings` do mesmo utilizador "
            "que `session_id`. Pode usar `query` para pré-filtrar mensagens com ILIKE antes de re-embedar "
            "(modo worker); se `query` for omitido, usa os vectores já persistidos. "
            "Pode ser lento — não chamar em cada turno."
        ),
        annotations=ToolAnnotations(readOnlyHint=False),
    )
    async def context_rebuild_kmeans(
        session_id: str,
        n_clusters: int = 8,
        model_version: str = "kmeans_v1",
        query: str | None = None,
    ) -> str:
        from app.config import get_settings

        st = get_settings()
        model = (st.context_embedding_model or "text-embedding-3-small").strip()
        like_lim = max(1, min(int(st.context_like_prefilter_limit), 200))
        try:
            sid = UUID(session_id.strip())
        except ValueError:
            return _json_response({"ok": False, "error": "session_id inválido"})
        k = max(2, min(int(n_clusters), 64))
        try:
            pool = await get_pg_pool()
        except Exception as e:
            return _json_response({"ok": False, "error": str(e)})

        async with pool.acquire() as conn:
            uid = await resolve_user_id_for_session(conn, sid)
            rows = await load_session_embeddings_for_anchor(conn, sid, uid, model=model)

            if query and query.strip():
                pattern = question_to_ilike_pattern(query)
                msgs = await ilike_candidate_messages(conn, sid, pattern=pattern, limit=like_lim)
                if len(msgs) < k:
                    return _json_response(
                        {
                            "ok": False,
                            "error": "poucos pontos após ILIKE; ajuste query ou like_limit",
                            "after_like": len(msgs),
                        }
                    )
                texts = [f"{m['role']}: {m['content']}"[:4000] for m in msgs]
                try:
                    vecs = await embed_texts(texts, model=model)
                except Exception as e:
                    return _json_response({"ok": False, "error": str(e)[:500]})

                def _fit() -> tuple[Any, int, list[int]]:
                    km, n_eff = fit_kmeans(vecs, k)
                    labels = [int(x) for x in km.labels_]
                    return km, n_eff, labels

                km, n_eff, labels = await asyncio.to_thread(_fit)
                sil = silhouette_optional(vecs, labels)
                centroids = [c.tolist() for c in km.cluster_centers_]
                sizes: list[int] = [0] * len(centroids)
                for lab in km.labels_:
                    sizes[int(lab)] += 1
                await replace_kmeans_centroids(
                    conn,
                    model_version=model_version,
                    n_clusters=len(centroids),
                    centroids=centroids,
                    n_points=sizes,
                )
                return _json_response(
                    {
                        "ok": True,
                        "mode": "embed_prefilter",
                        "n_points": len(vecs),
                        "n_clusters": len(centroids),
                        "n_eff": n_eff,
                        "model_version": model_version,
                        "silhouette": sil,
                    }
                )

            vectors: list[list[float]] = []
            ids: list[UUID] = []
            for r in rows:
                v = json_vec_to_list(r["embedding"])
                if len(v) < 8:
                    continue
                vectors.append(v)
                ids.append(r["session_id"])
            if len(vectors) < k:
                return _json_response(
                    {
                        "ok": False,
                        "error": "poucos pontos para KMeans",
                        "n_sessions": len(vectors),
                        "n_clusters_requested": k,
                    }
                )
            def _fit2() -> tuple[Any, int, list[int]]:
                km2, n_eff2 = fit_kmeans(vectors, k)
                labels2 = [int(x) for x in km2.labels_]
                return km2, n_eff2, labels2

            km, n_eff, labels = await asyncio.to_thread(_fit2)
            sil = silhouette_optional(vectors, labels)
            for i, sess in enumerate(ids):
                cid = int(km.labels_[i])
                await update_session_cluster(
                    conn,
                    session_id=sess,
                    cluster_id=cid,
                    model_version=model_version,
                )
            centroids = [c.tolist() for c in km.cluster_centers_]
            sizes = [0] * len(centroids)
            for lab in km.labels_:
                sizes[int(lab)] += 1
            await replace_kmeans_centroids(
                conn,
                model_version=model_version,
                n_clusters=len(centroids),
                centroids=centroids,
                n_points=sizes,
            )
        return _json_response(
            {
                "ok": True,
                "mode": "stored_embeddings",
                "n_sessions": len(vectors),
                "n_clusters": len(centroids),
                "n_eff": n_eff,
                "model_version": model_version,
                "silhouette": sil,
            }
        )

    @mcp.tool(
        name="context_retrieve_similar",
        description=(
            "Obrigatório por turno quando há PostgreSQL e `session_id`: recupera contexto semântico "
            "a partir da `query` natural. **Pré-filtro ILIKE** nas mensagens candidatas por sessão; "
            "**só depois** embeddings e ranking por similaridade de coseno (reduz custo vs janela cheia). "
            "readOnly. Custo: 1+ chamadas embeddings. Devolve JSON com `injected_context` em markdown."
        ),
        annotations=ToolAnnotations(readOnlyHint=True),
    )
    async def context_retrieve_similar(
        session_id: str,
        query: str,
        top_n: int = 5,
        top_m_per_session: int = 4,
        max_context_chars: int = 12000,
        exclude_session_id: str | None = None,
    ) -> str:
        from app.config import get_settings

        st = get_settings()
        model = (st.context_embedding_model or "text-embedding-3-small").strip()
        tn = max(1, min(int(top_n), int(st.context_retrieve_default_top_n * 3)))
        tm = max(1, min(int(top_m_per_session), int(st.context_retrieve_default_top_m * 2)))
        max_ch = max(500, min(int(max_context_chars), 100_000))
        q = (query or "").strip()
        if len(q) < 2:
            return _json_response({"ok": False, "error": "query demasiado curta"})
        try:
            sid = UUID(session_id.strip())
        except ValueError:
            return _json_response({"ok": False, "error": "session_id inválido"})
        ex: UUID | None = None
        if exclude_session_id:
            try:
                ex = UUID(exclude_session_id.strip())
            except ValueError:
                ex = None
        try:
            pool = await get_pg_pool()
        except Exception as e:
            return _json_response({"ok": False, "error": str(e)})
        try:
            qv = (await embed_texts([q], model=model))[0]
        except Exception as e:
            return _json_response({"ok": False, "error": f"embed:{e}"[:500]})

        async with pool.acquire() as conn:
            uid = await resolve_user_id_for_session(conn, sid)
            rows = await load_session_embeddings_for_anchor(conn, sid, uid, model=model)

            scored: list[tuple[float, UUID, int | None]] = []
            for r in rows:
                sess = r["session_id"]
                if ex is not None and sess == ex:
                    continue
                v = json_vec_to_list(r["embedding"])
                if len(v) != len(qv):
                    continue
                s = cosine_similarity(qv, v)
                cid = r.get("cluster_id")
                cid_i = int(cid) if cid is not None else None
                scored.append((s, sess, cid_i))
            scored.sort(key=lambda x: x[0], reverse=True)
            top_sessions = scored[:tn]

            sessions_out: list[dict[str, Any]] = []
            messages_preview: list[dict[str, Any]] = []
            blocks: list[str] = []
            like_report: list[dict[str, Any]] = []
            me_cache_hits = 0
            me_cache_misses = 0
            bs = max(1, min(int(st.context_message_embed_batch_size), 2048))

            win = max(8, int(st.context_message_candidate_window))
            like_lim = max(1, min(int(st.context_like_prefilter_limit), 200))
            for sim, su, cl in top_sessions:
                msgs, n_like, mode = await load_messages_for_retrieve(
                    conn,
                    su,
                    q,
                    like_limit=like_lim,
                    window_cap=win,
                )
                like_report.append(
                    {
                        "session_id": str(su),
                        "mode": mode,
                        "candidates": len(msgs),
                        "ilike_hits": n_like if mode == "ilike" else 0,
                    }
                )
                if not msgs:
                    continue
                texts = [f"{m['role']}: {m['content']}"[:6000] for m in msgs]
                if st.context_message_embeddings_enabled:
                    ids = [int(m["id"]) for m in msgs]
                    cached = await fetch_message_embeddings(conn, ids, model=model)
                    miss_msgs: list[dict[str, Any]] = []
                    qdim = len(qv)
                    for m in msgs:
                        mid = int(m["id"])
                        v = cached.get(mid)
                        if v is None or len(v) != qdim:
                            miss_msgs.append(m)
                    fresh: dict[int, list[float]] = {}
                    if miss_msgs:
                        t_miss = [
                            f"{m['role']}: {m['content']}"[:6000] for m in miss_msgs
                        ]
                        try:
                            m_miss = await embed_texts_batched(
                                t_miss, model=model, batch_size=bs
                            )
                        except Exception:
                            continue
                        if len(m_miss) != len(miss_msgs):
                            continue
                        fresh = {
                            int(m["id"]): m_miss[i] for i, m in enumerate(miss_msgs)
                        }
                    merged = merge_message_vectors_for_retrieve(
                        msgs, cached=cached, fresh=fresh, query_dim=qdim
                    )
                    if merged is None:
                        continue
                    mvecs, ch, cm = merged
                    me_cache_hits += ch
                    me_cache_misses += cm
                    if st.context_message_embed_writeback_on_retrieve and miss_msgs:
                        wb_rows = [
                            (int(m["id"]), su, model, fresh[int(m["id"])])
                            for m in miss_msgs
                            if int(m["id"]) in fresh
                        ]
                        if wb_rows:
                            try:
                                await upsert_message_embeddings_batch(conn, wb_rows)
                            except Exception:
                                _logger.exception(
                                    "context_retrieve_similar writeback message embeddings"
                                )
                else:
                    try:
                        mvecs = await embed_texts_batched(
                            texts, model=model, batch_size=bs
                        )
                    except Exception:
                        continue
                msg_scored: list[tuple[float, dict[str, Any]]] = []
                for m, mv, raw in zip(msgs, mvecs, texts):
                    sc = cosine_similarity(qv, mv)
                    msg_scored.append((sc, {"message_id": m["id"], "role": m["role"], "snippet": raw[:400]}))
                msg_scored.sort(key=lambda x: x[0], reverse=True)
                best = msg_scored[:tm]
                sessions_out.append(
                    {
                        "session_id": str(su),
                        "score": round(float(sim), 4),
                        "cluster_id": cl,
                    }
                )
                for sc, meta in best:
                    messages_preview.append(
                        {
                            "message_id": meta.get("message_id"),
                            "score": round(float(sc), 4),
                            "role": meta.get("role"),
                            "snippet": meta.get("snippet"),
                        }
                    )
                block_lines = [f"### Sessão `{su}` (sim={sim:.3f})"]
                for sc, meta in best:
                    block_lines.append(
                        f"- ({meta['role']}, score={sc:.3f}) {meta['snippet'][:800]}"
                    )
                blocks.append("\n".join(block_lines))

            injected = "\n\n".join(blocks)[:max_ch]
            if not injected.strip():
                injected = (
                    f"_{CONTEXT_RETRIEVE_EMPTY_INDEX_MARKER} ou sem embeddings — executar `context_embed_sessions` "
                    "para esta sessão/utilizador quando fizer sentido._"
                )
            prev_n = len(messages_preview[: tn * tm])
            like_sum = summarize_like_prefilter(like_report)
            _logger.info(
                "context_retrieve_similar session_prefix=%s sessions_out=%s messages_preview=%s "
                "placeholder=%s like_prefilter=%s",
                str(sid)[:8],
                len(sessions_out),
                prev_n,
                CONTEXT_RETRIEVE_EMPTY_INDEX_MARKER in injected,
                like_sum,
            )
            return _json_response(
                {
                    "ok": True,
                    "injected_context": injected,
                    "sessions": sessions_out,
                    "messages_preview": messages_preview[: tn * tm],
                    "like_prefilter": like_report,
                    "message_embedding_cache": {
                        "enabled": st.context_message_embeddings_enabled,
                        "hits": me_cache_hits,
                        "misses": me_cache_misses,
                    },
                }
            )

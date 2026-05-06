"""
Worker isolado: ILIKE → embeddings só em candidatos; opcional K-Means (env).

Uso (exemplo, a partir da pasta ``mcp_server``):
  CONTEXT_WORKER_SESSION_ID=<uuid> CONTEXT_WORKER_QUERY="texto" \\
    python -m context_retrieval.worker

Variáveis opcionais:
  CONTEXT_WORKER_EMBED=1   — gera embeddings dos candidatos ILIKE (JSON inclui dimensão).
  CONTEXT_WORKER_RUN_KMEANS=1 — K-Means sobre esses vectores (requer CONTEXT_WORKER_EMBED=1).
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from uuid import UUID

_mcp_root = Path(__file__).resolve().parent.parent
if str(_mcp_root) not in sys.path:
    sys.path.insert(0, str(_mcp_root))
_proj_root = _mcp_root.parent
if str(_proj_root) not in sys.path:
    sys.path.append(str(_proj_root))


def _truthy(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in ("1", "true", "yes", "on")


async def _main() -> None:
    from app.config import get_settings

    st = get_settings()
    raw_sid = (os.environ.get("CONTEXT_WORKER_SESSION_ID") or "").strip()
    query = (os.environ.get("CONTEXT_WORKER_QUERY") or "").strip()
    if not raw_sid or not query:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "Defina CONTEXT_WORKER_SESSION_ID e CONTEXT_WORKER_QUERY",
                },
                ensure_ascii=False,
            )
        )
        raise SystemExit(1)
    sid = UUID(raw_sid)
    from context_retrieval.embedder import embed_texts
    from context_retrieval.pool import get_pg_pool
    from context_retrieval.prefilter import load_messages_for_retrieve

    pool = await get_pg_pool()
    like_lim = max(1, min(int(st.context_like_prefilter_limit), 200))
    win = max(8, int(st.context_message_candidate_window))
    async with pool.acquire() as conn:
        msgs, n_like, mode = await load_messages_for_retrieve(
            conn,
            sid,
            query,
            like_limit=like_lim,
            window_cap=win,
        )
    out: dict = {
        "ok": True,
        "mode": mode,
        "ilike_hits": n_like,
        "candidate_count": len(msgs),
        "sample": [{"id": m["id"], "role": m["role"]} for m in msgs[:5]],
    }

    vecs: list[list[float]] | None = None
    if _truthy("CONTEXT_WORKER_EMBED") and msgs:
        texts = [f"{m['role']}: {str(m.get('content') or '')[:4000]}" for m in msgs]
        model = (st.context_embedding_model or "text-embedding-3-small").strip()
        vecs = await embed_texts(texts, model=model)
        out["embedding_dim"] = len(vecs[0]) if vecs else 0

    if _truthy("CONTEXT_WORKER_RUN_KMEANS") and vecs and len(vecs) >= 2:
        from context_retrieval.clustering import fit_kmeans, silhouette_optional

        k = min(8, len(vecs))
        km, n_eff = fit_kmeans(vecs, k)
        labels = [int(x) for x in km.labels_]
        out["kmeans_n_eff"] = n_eff
        out["silhouette"] = silhouette_optional(vecs, labels)

    print(json.dumps(out, ensure_ascii=False, default=str))


if __name__ == "__main__":
    asyncio.run(_main())

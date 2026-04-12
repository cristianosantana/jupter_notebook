#!/usr/bin/env python3
"""
Gera embeddings em ``session_embeddings`` a partir de ``conversation_messages`` no PostgreSQL.

Equivale à tool MCP ``context_embed_sessions``: usa o mesmo utilizador (ou anónimo) que a
sessão âncora e processa até ``limit`` sessões com transcript.

Uso (directório raiz do projecto ``project_mcp_v1``)::

    PYTHONPATH=. python scripts/embed_sessions_from_db.py --session-id <UUID>
    PYTHONPATH=. python scripts/embed_sessions_from_db.py --session-id <UUID> --limit 64
    PYTHONPATH=. python scripts/embed_sessions_from_db.py --session-id <UUID> --anchor-query "texto da pergunta"

Requer ``POSTGRES_*``, ``OPENAI_API_KEY`` e opcionalmente ``.env`` na raiz (carregado por ``app.config``).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from uuid import UUID


def _setup_path() -> Path:
    root = Path(__file__).resolve().parent.parent
    mcp = root / "mcp_server"
    for p in (str(root), str(mcp)):
        if p not in sys.path:
            sys.path.insert(0, p)
    return root


async def _async_main() -> int:
    _setup_path()
    parser = argparse.ArgumentParser(
        description="Grava embeddings de sessão (OpenAI) com base no transcript PostgreSQL.",
    )
    parser.add_argument(
        "--session-id",
        required=True,
        help="UUID de qualquer sessão do mesmo utilizador (âncora para listar peer sessions).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=32,
        help="Máximo de sessões a processar (tecto ainda limitado por Settings).",
    )
    parser.add_argument(
        "--anchor-query",
        default=None,
        help="Opcional: agregar só mensagens que passam ILIKE (como no retrieve).",
    )
    args = parser.parse_args()

    try:
        sid = UUID(str(args.session_id).strip())
    except ValueError:
        print(json.dumps({"ok": False, "error": "session_id inválido"}, ensure_ascii=False))
        return 2

    from context_retrieval.batch_embed import run_embed_sessions_for_anchor_session

    result = await run_embed_sessions_for_anchor_session(
        sid,
        limit=int(args.limit),
        anchor_query=(args.anchor_query or "").strip() or None,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


def main() -> None:
    raise SystemExit(asyncio.run(_async_main()))


if __name__ == "__main__":
    main()

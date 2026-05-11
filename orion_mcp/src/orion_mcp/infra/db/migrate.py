from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import asyncpg

from orion_mcp.core.config.settings import Settings

_logger = logging.getLogger(__name__)


async def _ensure_pgvector(conn: asyncpg.Connection) -> bool:
    """
    Tenta `CREATE EXTENSION vector`. Se o servidor não tiver o pgvector (ficheiro .control),
    a app continua sem memória longa em vector até o administrador instalar o pacote.
    """
    try:
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        return True
    except Exception as e:
        _logger.warning("CREATE EXTENSION vector falhou: %s", e)
    try:
        row = await conn.fetchval("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
        return row is not None
    except Exception:
        return False


async def _reconcile_memory_embedding_dim(conn: asyncpg.Connection, settings: Settings) -> None:
    """Alinha vector(n) da coluna embedding a ORION_EMBEDDING_DIMENSIONS se a tabela existir e estiver vazia."""
    dim = int(settings.embedding_dimensions)
    row = await conn.fetchrow(
        """
        SELECT a.atttypmod AS typmod
        FROM pg_class c
        JOIN pg_attribute a ON a.attrelid = c.oid
        WHERE c.relkind = 'r'
          AND c.relname = 'memory_embeddings'
          AND a.attname = 'embedding'
          AND a.attnum > 0
          AND NOT a.attisdropped
        """
    )
    if row is None or row["typmod"] is None or row["typmod"] <= 0:
        return
    current = int(row["typmod"])
    if current == dim:
        return
    n = await conn.fetchval("SELECT COUNT(*)::bigint FROM memory_embeddings")
    if n and n > 0:
        _logger.warning(
            "memory_embeddings.embedding está definida como vector(%s) mas "
            "ORION_EMBEDDING_DIMENSIONS=%s e a tabela tem %s linhas; não foi feita alteração automática.",
            current,
            dim,
            n,
        )
        return
    await conn.execute(
        f"ALTER TABLE memory_embeddings ALTER COLUMN embedding TYPE vector({dim})"
    )
    _logger.info(
        "Coluna memory_embeddings.embedding alinhada de vector(%s) para vector(%s) (tabela vazia).",
        current,
        dim,
    )


async def run_migrations(settings: Settings) -> None:
    if not settings.database_url:
        return
    conn = await asyncpg.connect(settings.database_url)
    try:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
              id TEXT PRIMARY KEY,
              applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """
        )
        here = Path(__file__).resolve().parent
        migrations_dir = here / "migrations"
        if not migrations_dir.is_dir():
            migrations_dir = here.parents[4] / "migrations"
        for path in sorted(migrations_dir.glob("*.sql")):
            mid = path.name
            done = await conn.fetchval("SELECT 1 FROM schema_migrations WHERE id = $1", mid)
            if done:
                continue
            if mid == "003_memory_embeddings_hnsw.sql":
                tbl = await conn.fetchval(
                    """
                    SELECT 1 FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = 'memory_embeddings'
                    """
                )
                if tbl is None:
                    _logger.warning(
                        "Migração %s adiada: tabela memory_embeddings ausente (migração 002 não aplicada).",
                        mid,
                    )
                    continue
                if not await _ensure_pgvector(conn):
                    _logger.warning("Migração %s adiada: extensão vector indisponível.", mid)
                    continue
                ext_ok = await conn.fetchval(
                    "SELECT 1 FROM pg_extension WHERE extname = 'vector'"
                )
                if ext_ok is None:
                    _logger.warning(
                        "Migração %s adiada: extensão vector não visível após CREATE EXTENSION.",
                        mid,
                    )
                    continue
                if int(settings.embedding_dimensions) > 2000:
                    _logger.info(
                        "Migração %s: HNSW não aplicável com ORION_EMBEDDING_DIMENSIONS=%s (>2000; "
                        "limite típico do pgvector). Marcação 003 como aplicada; a 004 regista-se sem "
                        "índice ANN (IVFFlat tem o mesmo limite).",
                        mid,
                        settings.embedding_dimensions,
                    )
                    await conn.execute("INSERT INTO schema_migrations (id) VALUES ($1)", mid)
                    continue
            if mid == "004_memory_embeddings_ivfflat.sql":
                tbl = await conn.fetchval(
                    """
                    SELECT 1 FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = 'memory_embeddings'
                    """
                )
                if tbl is None:
                    _logger.warning(
                        "Migração %s adiada: tabela memory_embeddings ausente.",
                        mid,
                    )
                    continue
                if not await _ensure_pgvector(conn):
                    _logger.warning("Migração %s adiada: extensão vector indisponível.", mid)
                    continue
                ext_ok = await conn.fetchval(
                    "SELECT 1 FROM pg_extension WHERE extname = 'vector'"
                )
                if ext_ok is None:
                    _logger.warning(
                        "Migração %s adiada: extensão vector não visível após CREATE EXTENSION.",
                        mid,
                    )
                    continue
                if int(settings.embedding_dimensions) <= 2000:
                    _logger.info(
                        "Migração %s omitida: dimensão ≤2000 (índice HNSW na 003). Marcada como aplicada.",
                        mid,
                    )
                    await conn.execute("INSERT INTO schema_migrations (id) VALUES ($1)", mid)
                    continue
                _logger.info(
                    "Migração %s: dimensão %s > 2000 — neste pgvector não há índice ANN (HNSW/IVFFlat) "
                    "acima de 2000 dim; retrieve_memory usa plano sequencial. Para ANN, usa "
                    "ORION_EMBEDDING_DIMENSIONS ≤ 2000. Marcada como aplicada.",
                    mid,
                    settings.embedding_dimensions,
                )
                await conn.execute("INSERT INTO schema_migrations (id) VALUES ($1)", mid)
                continue
            if mid == "002_memory_embeddings.sql":
                has_vec = await _ensure_pgvector(conn)
                if not has_vec:
                    _logger.warning(
                        "Migração %s adiada: instale pgvector no PostgreSQL (ex.: "
                        "`postgresql-16-pgvector` ou use imagem `pgvector/pgvector`). "
                        "A API arranca sem tabela memory_embeddings até a extensão existir.",
                        mid,
                    )
                    continue
                ext_ok = await conn.fetchval(
                    "SELECT 1 FROM pg_extension WHERE extname = 'vector'"
                )
                if ext_ok is None:
                    _logger.warning(
                        "Migração %s adiada: extensão vector não visível após CREATE EXTENSION.",
                        mid,
                    )
                    continue
            sql = path.read_text(encoding="utf-8")
            if mid == "002_memory_embeddings.sql":
                dim = int(settings.embedding_dimensions)
                token = "vector(1536)"
                if token not in sql:
                    raise RuntimeError(
                        f"{mid} deve conter o placeholder {token} "
                        "(substituído em runtime por ORION_EMBEDDING_DIMENSIONS)."
                    )
                sql = sql.replace(token, f"vector({dim})", 1)
            try:
                await conn.execute(sql)
            except Exception as e:
                # Camada extra: se o pré-check falhar noutro modo de instalação, não derrubar o arranque.
                if mid == "002_memory_embeddings.sql":
                    _logger.warning(
                        "Migração %s não aplicada (SQL falhou; confirma pgvector no servidor): %s",
                        mid,
                        e,
                    )
                    continue
                if mid == "003_memory_embeddings_hnsw.sql":
                    _logger.warning(
                        "Migração %s não aplicada (HNSW indisponível ou pgvector antigo?): %s",
                        mid,
                        e,
                    )
                    continue
                if mid == "004_memory_embeddings_ivfflat.sql":
                    _logger.warning(
                        "Migração %s não aplicada (IVFFlat indisponível ou pgvector antigo?): %s",
                        mid,
                        e,
                    )
                    continue
                raise
            await conn.execute("INSERT INTO schema_migrations (id) VALUES ($1)", mid)
            _logger.info("Applied migration %s", mid)
        await _reconcile_memory_embedding_dim(conn, settings)
    finally:
        await conn.close()


def main() -> None:
    from orion_mcp.core.config.settings import get_settings

    asyncio.run(run_migrations(get_settings()))


if __name__ == "__main__":
    main()

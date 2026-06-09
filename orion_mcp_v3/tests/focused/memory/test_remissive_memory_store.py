from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from orion_mcp_v3.memory.remissive_memory_store import RemissiveMemoryStore
from orion_mcp_v3.memory.remissive_models import (
    CompressionLogEntry,
    RemissiveEssenceItem,
    RemissiveKnowledgeItem,
    SupervisedMemoryBatch,
)


MIGRATION = Path("src/orion_mcp_v3/infra/postgres/migrations/010_remissive_memory_schema.sql")
WIDE_LOG_MIGRATION = Path(
    "src/orion_mcp_v3/infra/postgres/migrations/011_memory_compression_log_wide_keys.sql"
)
WIDE_ESSENCE_MIGRATION = Path(
    "src/orion_mcp_v3/infra/postgres/migrations/012_memory_essence_wide_keys.sql"
)


def test_remissive_schema_migration_defines_v2_tables() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")

    assert 'CREATE TABLE "public"."memory_curta"' in sql
    assert '"id" SERIAL' in sql
    assert '"context_key" VARCHAR(100) NOT NULL' in sql
    assert 'UNIQUE ("context_key")' in sql
    assert '"validated_answer" TEXT NOT NULL' in sql
    assert 'CREATE TABLE "public"."memory_embeddings"' in sql
    assert '"origin_id" INTEGER NOT NULL' in sql
    assert '"origin_type" VARCHAR(50) NOT NULL' in sql
    assert 'FOREIGN KEY ("origin_id")' in sql
    assert 'ON DELETE CASCADE' in sql
    assert 'CREATE TABLE "public"."memory_essence"' in sql
    assert 'UNIQUE ("user_id", "theme")' in sql
    assert 'CREATE TABLE "public"."memory_compression_log"' in sql
    assert '"batch_key" VARCHAR(100) NOT NULL' in sql
    assert 'UNIQUE ("batch_key")' in sql


def test_memory_compression_log_wide_key_migration_extends_varchar_limits() -> None:
    sql = WIDE_LOG_MIGRATION.read_text(encoding="utf-8")

    assert 'ALTER TABLE "public"."memory_compression_log"' in sql
    assert 'ALTER COLUMN "batch_key" TYPE VARCHAR(255)' in sql
    assert 'ALTER COLUMN "from_state" TYPE VARCHAR(255)' in sql
    assert 'ALTER COLUMN "to_state" TYPE VARCHAR(255)' in sql


def test_memory_essence_wide_key_migration_extends_varchar_limits() -> None:
    sql = WIDE_ESSENCE_MIGRATION.read_text(encoding="utf-8")

    assert 'ALTER TABLE "public"."memory_essence"' in sql
    assert 'ALTER COLUMN "theme" TYPE VARCHAR(255)' in sql
    assert 'ALTER COLUMN "confidence" TYPE VARCHAR(50)' in sql


def _pool_with_conn(conn: AsyncMock) -> MagicMock:
    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    tx = MagicMock()
    tx.__aenter__ = AsyncMock(return_value=None)
    tx.__aexit__ = AsyncMock(return_value=False)
    conn.transaction = MagicMock(return_value=tx)
    return pool


@pytest.mark.asyncio
async def test_upsert_knowledge_replaces_index_embeddings_by_origin_id() -> None:
    embed = AsyncMock()
    embed.embed.return_value = [[0.1, 0.2], [0.3, 0.4]]

    conn = AsyncMock()
    conn.fetchval.return_value = 101
    conn.execute.return_value = "INSERT 0 1"

    store = RemissiveMemoryStore(_pool_with_conn(conn), embed)
    item = RemissiveKnowledgeItem(
        user_id="sistema_background",
        category="Financeiro",
        context_key="fechamento_gerencial_2026_05",
        validated_answer="Faturamento validado de maio.",
        recent_questions=("Como foi maio?",),
        key_metrics={"faturamento": 2696125.56},
        index_questions=(
            "Qual foi o faturamento de maio de 2026?",
            "Quanto a empresa vendeu em maio 26?",
        ),
        consolidated_at=datetime(2026, 6, 9, tzinfo=timezone.utc),
    )

    origin_id = await store.upsert_knowledge(item)

    assert origin_id == 101
    embed.embed.assert_awaited_once_with(list(item.index_questions))
    conn.fetchval.assert_awaited_once()
    execute_sql = "\n".join(str(call.args[0]) for call in conn.execute.await_args_list)
    assert 'DELETE FROM "public"."memory_embeddings"' in execute_sql
    assert '"origin_id" = $1' in execute_sql
    assert 'INSERT INTO "public"."memory_embeddings"' in execute_sql
    assert conn.execute.await_count == 3


@pytest.mark.asyncio
async def test_persist_batch_writes_essence_and_compression_log() -> None:
    embed = AsyncMock()
    embed.embed.return_value = [[0.1, 0.2]]

    conn = AsyncMock()
    conn.fetchval.return_value = 102
    conn.execute.return_value = "INSERT 0 1"

    store = RemissiveMemoryStore(_pool_with_conn(conn), embed)
    batch = SupervisedMemoryBatch(
        knowledge=(
            RemissiveKnowledgeItem(
                user_id="sistema_background",
                category="Financeiro",
                context_key="ticket_medio_maio_2026",
                validated_answer="Ticket medio validado de maio.",
                index_questions=("Qual foi o ticket medio de maio?",),
            ),
        ),
        essence=(
            RemissiveEssenceItem(
                user_id="sistema_background",
                theme="fechamento_mensal",
                key_finding="Maio foi validado como referencia de fechamento.",
                confidence="high",
            ),
        ),
        compression_log=CompressionLogEntry(
            user_id="sistema_background",
            from_state="conversation_state",
            to_state="memory_v2",
            messages_compressed=3,
            compression_ratio=0.4,
            what_was_kept="Indicadores validados.",
            what_was_dropped="Saudacoes e tentativas intermediarias.",
            batch_key="2026-06-09T00:00Z:2026-06-10T00:00Z:sistema_background",
        ),
    )

    written_ids = await store.persist_batch(batch)

    assert written_ids == [102]
    execute_sql = "\n".join(str(call.args[0]) for call in conn.execute.await_args_list)
    assert 'INSERT INTO "public"."memory_essence"' in execute_sql
    assert 'ON CONFLICT ("user_id", "theme")' in execute_sql
    assert 'INSERT INTO "public"."memory_compression_log"' in execute_sql
    assert 'ON CONFLICT ("batch_key")' in execute_sql


@pytest.mark.asyncio
async def test_write_compression_log_preserves_long_audit_fields_for_wide_schema() -> None:
    embed = AsyncMock()
    conn = AsyncMock()
    conn.execute.return_value = "INSERT 0 1"

    from_state = "conversation_state:" + ("origem_muito_longa_" * 5)
    to_state = "memory_v2:" + ("destino_muito_longo_" * 5)
    batch_key = "2026-06-03T00:00:00+00:00:2026-06-09T00:00:00+00:00:sistema_background"
    store = RemissiveMemoryStore(_pool_with_conn(conn), embed)
    await store.write_compression_log(
        CompressionLogEntry(
            user_id="sistema_background",
            from_state=from_state,
            to_state=to_state,
            batch_key=batch_key,
        )
    )

    args = conn.execute.await_args.args
    assert args[1] == batch_key
    assert args[3] == from_state
    assert args[4] == to_state

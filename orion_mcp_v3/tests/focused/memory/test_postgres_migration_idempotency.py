from __future__ import annotations

from pathlib import Path


def test_legacy_memory_embeddings_migration_is_idempotent_after_v2_schema() -> None:
    sql = Path(
        "src/orion_mcp_v3/infra/postgres/migrations/003_memory_embeddings.sql"
    ).read_text(encoding="utf-8")

    alter_pos = sql.find("ADD COLUMN IF NOT EXISTS type")
    comment_pos = sql.find("COMMENT ON COLUMN memory_embeddings.type")

    assert alter_pos != -1
    assert comment_pos != -1
    assert alter_pos < comment_pos

from __future__ import annotations

from orion_mcp_v3.public_chat.infrastructure.postgres.migrate import read_migration


def test_no_semantic_cache_on_responses() -> None:
    sql = read_migration("001_public_chat_schema.sql")
    assert '"embedding"' not in sql
    assert "ivfflat" not in sql.lower()
    assert "hnsw" not in sql.lower()
    assert "UNIQUE (\"topic\", \"semantic_hash\")" in sql or 'UNIQUE ("topic", "semantic_hash")' in sql

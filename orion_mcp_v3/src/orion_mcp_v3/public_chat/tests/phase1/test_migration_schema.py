from __future__ import annotations

from orion_mcp_v3.public_chat.infrastructure.postgres import list_migration_files, read_migration


def test_migration_schema() -> None:
    files = list_migration_files()
    assert files == [
        "001_public_chat_schema.sql",
        "002_query_normalized.sql",
        "003_topic_varchar256.sql",
    ]

    sql = read_migration("001_public_chat_schema.sql")

    assert 'CREATE TABLE IF NOT EXISTS "public"."public_chat_questions"' in sql
    assert '"semantic_hash" VARCHAR(64) NOT NULL' in sql
    assert '"query_original" TEXT NOT NULL' in sql
    assert "query_normalized" not in sql
    assert 'CREATE TABLE IF NOT EXISTS "public"."public_chat_responses"' in sql
    assert 'UNIQUE ("topic", "semantic_hash")' in sql
    assert '"answer_payload" JSONB NOT NULL' in sql
    assert '"knowledge_fingerprint" VARCHAR(64) NOT NULL' in sql
    assert '"embedding"' not in sql
    assert "ivfflat" not in sql.lower()
    assert "hnsw" not in sql.lower()
    assert 'CREATE TABLE IF NOT EXISTS "public"."public_chat_question_responses"' in sql

    sql_002 = read_migration("002_query_normalized.sql")
    assert '"query_normalized" TEXT NULL' in sql_002
    assert "idx_pcq_intent_cache" in sql_002

    sql_003 = read_migration("003_topic_varchar256.sql")
    assert 'ALTER COLUMN "topic" TYPE VARCHAR(256)' in sql_003

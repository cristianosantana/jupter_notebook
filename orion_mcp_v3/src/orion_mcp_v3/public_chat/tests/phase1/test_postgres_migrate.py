from __future__ import annotations

from orion_mcp_v3.public_chat.infrastructure.postgres.migrate import (
    list_migration_files,
    split_sql_statements,
)


def test_list_migration_files_is_sorted() -> None:
    files = list_migration_files()
    assert files == sorted(files)
    assert "001_public_chat_schema.sql" in files


def test_split_sql_statements_ignores_comment_only_lines() -> None:
    sql = """
-- comment
CREATE TABLE foo (id INT);
"""
    statements = split_sql_statements(sql)
    assert len(statements) == 1
    assert "CREATE TABLE foo" in statements[0]

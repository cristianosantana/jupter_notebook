"""Parser de cabeçalho @mcp_query_meta nos ficheiros SQL."""

from __future__ import annotations

from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_MCP = _ROOT / "mcp_server"
import sys

if str(_MCP) not in sys.path:
    sys.path.insert(0, str(_MCP))

from query_sql_meta import parse_sql_file  # noqa: E402


def test_parse_sql_file_minimal(tmp_path: Path) -> None:
    p = tmp_path / "demo_query.sql"
    p.write_text(
        """/* @mcp_query_meta
resource_description: "Teste."
when_to_use: |
  Uma linha.
output_shape: json_aggregate
@mcp_query_meta */

SELECT 1 AS resultado;
""",
        encoding="utf-8",
    )
    meta, body = parse_sql_file(p)
    assert meta["query_id"] == "demo_query"
    assert meta["output_shape"] == "json_aggregate"
    assert "SELECT 1" in body
    assert "mcp_query_meta" not in body


def test_parse_sql_file_not_confused_with_list(tmp_path: Path) -> None:
    p = tmp_path / "q2.sql"
    p.write_text(
        """/* @mcp_query_meta
resource_description: "x"
when_to_use: "y"
output_shape: tabular_multiline
not_confused_with:
  - a
  - b
@mcp_query_meta */
WITH x AS (SELECT 1) SELECT * FROM x;
""",
        encoding="utf-8",
    )
    meta, _ = parse_sql_file(p)
    assert meta["not_confused_with"] == ["a", "b"]


def test_parse_rejects_query_id_mismatch(tmp_path: Path) -> None:
    p = tmp_path / "good_stem.sql"
    p.write_text(
        """/* @mcp_query_meta
query_id: wrong
resource_description: "x"
when_to_use: "y"
output_shape: json_aggregate
@mcp_query_meta */
SELECT 1;
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="coincidir"):
        parse_sql_file(p)


def test_parse_rejects_multiple_statements(tmp_path: Path) -> None:
    p = tmp_path / "multi.sql"
    p.write_text(
        """/* @mcp_query_meta
resource_description: "x"
when_to_use: "y"
output_shape: json_aggregate
@mcp_query_meta */
SELECT 1;
SELECT 2;
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="múltiplas"):
        parse_sql_file(p)

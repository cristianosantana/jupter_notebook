"""Testes para serialização JSON do módulo mcp_server.db (datetime, payloads compactos)."""

from __future__ import annotations

import json
import sys
from datetime import date, datetime, time
from pathlib import Path

_MCP = Path(__file__).resolve().parent.parent / "mcp_server"
if str(_MCP) not in sys.path:
    sys.path.insert(0, str(_MCP))

import db  # noqa: E402


class TestJsonDefault:
    def test_datetime_isoformat(self) -> None:
        dt = datetime(2026, 3, 30, 14, 21, 42)
        raw = json.dumps({"t": dt}, default=db._json_default)
        data = json.loads(raw)
        assert "2026-03-30" in data["t"]

    def test_date_isoformat(self) -> None:
        d = date(2026, 3, 30)
        raw = json.dumps({"d": d}, default=db._json_default)
        assert json.loads(raw)["d"] == "2026-03-30"

    def test_time_isoformat(self) -> None:
        t = time(14, 21, 42)
        raw = json.dumps({"t": t}, default=db._json_default)
        assert "14:21:42" in json.loads(raw)["t"]

    def test_rows_to_json_payload_with_datetime_row(self) -> None:
        rows = [{"id": 1, "when": datetime(2026, 1, 1, 12, 0, 0)}]
        s = db.rows_to_json_payload(
            rows, query_id="q", limit=10, offset=0, summarized=None
        )
        out = json.loads(s)
        assert out["row_count"] == 1
        assert "2026" in out["rows"][0]["when"]
        assert "payload_note" in out


class TestCompactPayload:
    def test_compact_includes_sample_and_metadata(self) -> None:
        rows = [{"a": i} for i in range(100)]
        s = db.rows_to_compact_json_payload(
            rows,
            query_id="test_q",
            limit=10000,
            offset=0,
            summarized="resumo curto",
            sample_size=5,
        )
        out = json.loads(s)
        assert out["query_id"] == "test_q"
        assert out["row_count"] == 100
        assert len(out["rows_sample"]) == 5
        assert out["llm_summary"] == "resumo curto"
        assert "note" not in out

    def test_compact_without_summary_has_note(self) -> None:
        rows = [{"x": 1}]
        s = db.rows_to_compact_json_payload(
            rows,
            query_id="q",
            limit=10,
            offset=0,
            summarized=None,
        )
        out = json.loads(s)
        assert out["llm_summary"] is None
        assert "note" in out

    def test_sampling_preview_small(self) -> None:
        rows = [{"n": i} for i in range(200)]
        s = db.rows_to_sampling_preview_payload(rows, query_id="q", sample_size=10)
        out = json.loads(s)
        assert out["row_count"] == 200
        assert len(out["rows_sample"]) == 10

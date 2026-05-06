"""Registo e carga de datasets de analytics."""

import json
from pathlib import Path
from uuid import UUID

import pytest

from app.analytics_session_datasets import (
    get_dataset_id_for_cache_key,
    load_dataset_for_aggregate,
    register_run_analytics_result,
)
from app.config import Settings, get_settings


def test_register_and_load_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        Settings,
        "resolve_analytics_dataset_spill_dir",
        lambda self: tmp_path,
    )
    get_settings.cache_clear()
    md: dict = {}
    payload = json.dumps(
        {
            "query_id": "q_test",
            "row_count": 2,
            "rows": [{"a": 1, "b": 2}, {"a": 3, "b": 4}],
        },
        ensure_ascii=False,
    )
    ds = register_run_analytics_result(
        md,
        full_result_text=payload,
        args={"query_id": "q_test"},
        cache_key="ck1",
        session_id=UUID("00000000-0000-0000-0000-000000000042"),
        settings=get_settings(),
    )
    assert ds is not None
    assert get_dataset_id_for_cache_key(md, "ck1") == ds
    rows, meta = load_dataset_for_aggregate(md, ds, get_settings())
    assert rows is not None
    assert len(rows) == 2
    assert meta.get("query_id") == "q_test"
    get_settings.cache_clear()


def test_register_skips_truncated_cache_marker():
    md: dict = {}
    t = register_run_analytics_result(
        md,
        full_result_text='{"rows":[]}\n\n[truncado mcp_cache_entry_max_chars]',
        args={},
        cache_key="x",
        session_id=None,
        settings=get_settings(),
    )
    assert t is None

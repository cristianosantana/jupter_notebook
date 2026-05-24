"""Serialização e eventos do módulo analytics_pipeline_trace."""

from __future__ import annotations

import json
import logging

import pytest

from orion_mcp_v3.contracts.cognitive_plan import CognitivePlan, IntentType
from orion_mcp_v3.runtime.analytics_pipeline_trace import (
    log_pipeline_event,
    snapshot_cognitive_plan,
)


def test_log_pipeline_event_emits_json(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="orion.analytics.pipeline")
    log_pipeline_event(
        etapa="teste",
        fase="pre",
        conversation_id="cid-1",
        dados={"x": 1, "nested": {"a": "b"}},
    )
    recs = [r for r in caplog.records if r.name == "orion.analytics.pipeline"]
    assert len(recs) == 1
    payload = json.loads(recs[0].message)
    assert payload["canal"] == "analytics_pipeline"
    assert payload["etapa"] == "teste"
    assert payload["fase"] == "pre"
    assert payload["conversation_id"] == "cid-1"
    assert payload["dados"]["x"] == 1


def test_configure_pipeline_file_logging_writes_jsonl(tmp_path) -> None:
    from orion_mcp_v3.config.settings import get_settings_uncached
    from orion_mcp_v3.runtime.analytics_pipeline_trace import (
        configure_pipeline_file_logging,
        log_pipeline_event,
        shutdown_pipeline_file_logging,
    )

    log_dir = tmp_path / "pipe_logs"
    s = get_settings_uncached(
        analytics_pipeline_trace=True,
        analytics_pipeline_log_dir=str(log_dir),
        _env_file=None,
    )
    path = configure_pipeline_file_logging(s)
    assert path is not None
    assert path.parent == log_dir.resolve()
    assert path.name.startswith("analytics_pipeline_")
    assert path.suffix == ".jsonl"
    assert not path.exists()

    log_pipeline_event(etapa="x", fase="pre", dados={"k": 1})
    assert path.exists()
    shutdown_pipeline_file_logging()

    text = path.read_text(encoding="utf-8").strip()
    assert text
    line = text.splitlines()[0]
    payload = json.loads(line)
    assert payload["etapa"] == "x"
    assert payload["dados"]["k"] == 1


def test_snapshot_cognitive_plan_minimal() -> None:
    cp = CognitivePlan(
        intent_type=IntentType.ANALYTICAL,
        needs_analytics=True,
        confidence=0.72,
        metrics=("revenue",),
    )
    snap = snapshot_cognitive_plan(cp)
    assert snap["needs_analytics"] is True
    assert snap["intent_type"] == "analytical"
    assert "revenue" in snap["metrics"]

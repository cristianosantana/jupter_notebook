from __future__ import annotations

import os
import uuid
from typing import Any

from orion_mcp.core.data_engine.schema_inference import infer_schema
from orion_mcp.core.data_engine.sampler import build_sample
from orion_mcp.core.data_engine.summary_builder import build_summary
from orion_mcp.core.data_engine.value_extractor import extract_insights
from orion_mcp.infra.observability.drl_session_log import append_drl_step
from orion_mcp.infra.observability.metrics import DRL_BUNDLES_BUILT

_DRL_LOG_KEY = "_orion_drl_log_session_id"


def pop_log_session_id(params: dict[str, Any]) -> str | None:
    raw = params.pop(_DRL_LOG_KEY, None)
    if raw is None:
        return None
    s = str(raw).strip()
    return s or None


def build_drl_bundle(
    rows: list[dict[str, Any]],
    *,
    query_id: str,
    log_session_id: str | None = None,
) -> dict[str, Any]:
    sid = (log_session_id or "").strip() or (os.environ.get("ORION_DRL_LOG_SESSION_ID") or "").strip() or None
    append_drl_step(
        "drl_rows_loaded",
        {"query_id": query_id, "row_count": len(rows)},
        session_id=sid,
    )
    schema = infer_schema(rows)
    append_drl_step("drl_schema_inferred", {"query_id": query_id, "schema": schema}, session_id=sid)
    summary = build_summary(rows, schema)
    append_drl_step(
        "drl_summary_built",
        {"query_id": query_id, "summary_keys": list(summary.keys()), "metrics_keys": list((summary.get("metrics") or {}).keys())},
        session_id=sid,
    )
    insights = extract_insights(summary)
    append_drl_step("drl_insights_extracted", {"query_id": query_id, "insights": insights}, session_id=sid)
    sample = build_sample(rows, schema)
    append_drl_step(
        "drl_sample_built",
        {
            "query_id": query_id,
            "top_n": len(sample.get("top") or []),
            "bottom_n": len(sample.get("bottom") or []),
            "outliers_n": len(sample.get("outliers") or []),
        },
        session_id=sid,
    )
    dataset_id = str(uuid.uuid4())
    bundle = {
        "dataset_id": dataset_id,
        "drl_summary": summary,
        "drl_insights": insights,
        "drl_sample": sample,
        "drl_schema": schema,
    }
    append_drl_step("drl_bundle_ready", {"query_id": query_id, "dataset_id": dataset_id}, session_id=sid)
    DRL_BUNDLES_BUILT.inc()
    return bundle

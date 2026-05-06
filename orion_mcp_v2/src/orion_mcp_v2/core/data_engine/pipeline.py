from __future__ import annotations

from typing import TYPE_CHECKING, Any

from orion_mcp_v2.core.data_engine.pipeline_skill_merge import merge_skill_aggregate
from orion_mcp_v2.core.data_engine.schema_inference import infer_schema
from orion_mcp_v2.core.data_engine.sampler import build_sample
from orion_mcp_v2.core.data_engine.summary_builder import build_summary
from orion_mcp_v2.core.data_engine.value_extractor import extract_insights

if TYPE_CHECKING:
    from orion_mcp_v2.config.settings import Settings


def run_data_pipeline(
    rows: list[dict[str, Any]],
    *,
    query_id: str | None = None,
    intent: str | None = None,
    settings: "Settings | None" = None,
) -> dict[str, Any]:
    _ = intent
    schema = infer_schema(rows)
    summary = build_summary(rows, schema)
    insights = extract_insights(summary)
    sample = build_sample(rows, schema)
    out: dict[str, Any] = {
        "summary": summary,
        "insights": insights,
        "sample": sample,
        "row_count": len(rows),
        "schema": schema,
    }
    return merge_skill_aggregate(out, rows, query_id=query_id, settings=settings)

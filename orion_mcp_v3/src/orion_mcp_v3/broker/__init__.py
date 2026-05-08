"""Broker analítico: planner, SQL seguro, agregações e amostragem."""

from orion_mcp_v3.broker.aggregators import (
    aggregate_groups,
    aggregate_ranking,
    aggregate_temporal_series,
    group_by,
    month_bounds,
    normalize_metrics,
    time_series,
    top_n,
)
from orion_mcp_v3.broker.chunking import chunk_rows, estimate_chunk_tokens, rows_blob
from orion_mcp_v3.broker.evidence_builder import EvidenceBuilder, evidence_block_to_digest
from orion_mcp_v3.broker.data_pipeline import DataPipeline
from orion_mcp_v3.broker.map_reduce import distill_with_semantic_merge, semantic_merge_sections
from orion_mcp_v3.broker.executor import AnalyticsExecutor, AnalyticsResult
from orion_mcp_v3.broker.planner import (
    build_query_plan,
    infer_aggregation_hints,
    infer_analytics_strategy,
    plan_from_natural_language,
)
from orion_mcp_v3.broker.reducers import (
    ChunkReducer,
    insights_from_numeric_spread,
    merge_cognitive_artifacts,
)
from orion_mcp_v3.broker.samplers import (
    outlier_sampler,
    recent_sampler,
    sample_outliers_structured,
    sample_recent_structured,
    sample_stratified_keys,
)
from orion_mcp_v3.broker.sql_compiler import (
    CompiledSql,
    SqlAllowlist,
    SqlCompilationError,
    compile_select,
)

__all__ = [
    "AnalyticsExecutor",
    "AnalyticsResult",
    "chunk_rows",
    "ChunkReducer",
    "DataPipeline",
    "estimate_chunk_tokens",
    "CompiledSql",
    "SqlAllowlist",
    "SqlCompilationError",
    "compile_select",
    "distill_with_semantic_merge",
    "EvidenceBuilder",
    "evidence_block_to_digest",
    "aggregate_groups",
    "aggregate_ranking",
    "aggregate_temporal_series",
    "group_by",
    "insights_from_numeric_spread",
    "merge_cognitive_artifacts",
    "normalize_metrics",
    "build_query_plan",
    "infer_aggregation_hints",
    "infer_analytics_strategy",
    "month_bounds",
    "outlier_sampler",
    "sample_outliers_structured",
    "sample_recent_structured",
    "sample_stratified_keys",
    "plan_from_natural_language",
    "semantic_merge_sections",
    "recent_sampler",
    "rows_blob",
    "time_series",
    "top_n",
]

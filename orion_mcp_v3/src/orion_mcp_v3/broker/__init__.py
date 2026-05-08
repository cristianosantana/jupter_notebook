"""Broker analítico: planner, SQL seguro, agregações e amostragem."""

from orion_mcp_v3.broker.aggregators import group_by, month_bounds, time_series, top_n
from orion_mcp_v3.broker.chunking import chunk_rows, estimate_chunk_tokens, rows_blob
from orion_mcp_v3.broker.data_pipeline import DataPipeline
from orion_mcp_v3.broker.executor import AnalyticsExecutor, AnalyticsResult
from orion_mcp_v3.broker.planner import infer_aggregation_hints, plan_from_natural_language
from orion_mcp_v3.broker.reducers import ChunkReducer
from orion_mcp_v3.broker.samplers import outlier_sampler, recent_sampler
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
    "group_by",
    "infer_aggregation_hints",
    "month_bounds",
    "outlier_sampler",
    "plan_from_natural_language",
    "recent_sampler",
    "rows_blob",
    "time_series",
    "top_n",
]

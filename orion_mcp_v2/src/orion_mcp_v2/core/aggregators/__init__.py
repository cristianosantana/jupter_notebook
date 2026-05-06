from __future__ import annotations

from orion_mcp_v2.core.aggregators.aggregator_protocol import RowsAggregator
from orion_mcp_v2.core.aggregators.aggregator_registry import (
    get_aggregator,
    registered_query_ids,
    register_aggregator,
)
from orion_mcp_v2.core.aggregators.cross_selling_aggregate import CrossSellingAggregator

__all__ = [
    "RowsAggregator",
    "CrossSellingAggregator",
    "get_aggregator",
    "registered_query_ids",
    "register_aggregator",
]

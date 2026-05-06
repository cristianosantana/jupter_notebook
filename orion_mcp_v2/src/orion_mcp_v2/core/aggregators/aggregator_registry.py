from __future__ import annotations

from typing import Any, Callable

from orion_mcp_v2.core.aggregators.aggregator_protocol import RowsAggregator
from orion_mcp_v2.core.aggregators.cross_selling_aggregate import CrossSellingAggregator

AggregatorFactory = Callable[[], RowsAggregator]

_REGISTRY: dict[str, AggregatorFactory] = {
    "cross_selling": lambda: CrossSellingAggregator(),
}


def registered_query_ids() -> frozenset[str]:
    return frozenset(_REGISTRY.keys())


def get_aggregator(query_id: str) -> RowsAggregator | None:
    factory = _REGISTRY.get(query_id)
    if factory is None:
        return None
    return factory()


def register_aggregator(query_id: str, factory: AggregatorFactory) -> None:
    """Extensão/testes: regista um agregador para um query_id."""
    _REGISTRY[query_id] = factory

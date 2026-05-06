from orion_mcp_v2.core.aggregators.aggregator_registry import (
    get_aggregator,
    registered_query_ids,
    register_aggregator,
)
from orion_mcp_v2.core.aggregators.cross_selling_aggregate import CrossSellingAggregator


def test_cross_selling_registered():
    assert "cross_selling" in registered_query_ids()
    a = get_aggregator("cross_selling")
    assert isinstance(a, CrossSellingAggregator)
    assert get_aggregator("ticket_medio_concessionaria_agg") is None


def test_register_aggregator_extension():
    import orion_mcp_v2.core.aggregators.aggregator_registry as reg_mod

    register_aggregator("__test_agg__", lambda: CrossSellingAggregator(top_n=3))
    try:
        g = get_aggregator("__test_agg__")
        assert isinstance(g, CrossSellingAggregator)
    finally:
        reg_mod._REGISTRY.pop("__test_agg__", None)

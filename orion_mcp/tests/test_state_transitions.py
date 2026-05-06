from orion_mcp.core.state.turn_hints import ChatTurnHints
from orion_mcp.core.state.models import State
from orion_mcp.core.state.transitions import update_state
from orion_mcp.mcp_adapter.queries import ALLOWED_QUERY_IDS


def test_update_state_format_only() -> None:
    s = update_state(State(), "tabela")
    assert s.intent == "format_only"


def test_update_state_force_refresh() -> None:
    s = update_state(State(), "atualizar métricas")
    assert s.flags.get("force_refresh") is True


def test_update_state_hints_domain_and_dates() -> None:
    qid = next(iter(ALLOWED_QUERY_IDS))
    hints = ChatTurnHints(
        query_id=qid,
        date_from="2024-01-01",
        date_to="2024-12-31",
        limit=99,
        offset=1,
        summarize=False,
    )
    s = update_state(State(), "olá", hints)
    assert s.flags.get("domain_query_id") == qid
    assert s.flags.get("domain_query_extra") == {
        "limit": 99,
        "offset": 1,
        "summarize": False,
    }
    assert s.filters.get("date_from") == "2024-01-01"
    assert s.filters.get("date_to") == "2024-12-31"


def test_update_state_hints_clears_domain_when_no_query_id() -> None:
    qid = next(iter(ALLOWED_QUERY_IDS))
    s0 = update_state(State(), "a", ChatTurnHints(query_id=qid))
    assert s0.flags.get("domain_query_id") == qid
    s1 = update_state(s0, "b", ChatTurnHints())
    assert s1.flags.get("domain_query_id") is None

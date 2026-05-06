from orion_mcp_v2.core.decision.engine import BusinessIntent, decide_turn


def test_decide_ticket_intent():
    p = decide_turn("qual o ticket médio por concessionária?", date_from="2026-01-01", date_to="2026-01-31")
    assert p.intent == BusinessIntent.FATURAMENTO
    assert "ticket" in p.query_id


def test_decide_quality():
    p = decide_turn("taxa de retrabalho na oficina", date_from=None, date_to=None)
    assert p.intent == BusinessIntent.QUALIDADE


def test_decide_combo_cross_selling():
    p = decide_turn(
        "quais combo são mais lucrativos? top 10",
        date_from="2025-01-01",
        date_to="2025-03-31",
    )
    assert p.intent == BusinessIntent.FATURAMENTO
    assert p.query_id == "cross_selling"

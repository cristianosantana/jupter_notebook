from orion_mcp_v2.config.settings import Settings
from orion_mcp_v2.core.data_engine.pipeline_skill_merge import merge_skill_aggregate


def test_merge_adds_skill_aggregate_for_cross_selling():
    rows = [
        {
            "servico_A_id": 1,
            "servico_B_id": 2,
            "frequencia_combo": 2,
            "receita_combo": 100.0,
        },
    ]
    base = {"summary": {}, "insights": [], "sample": [], "row_count": 1, "schema": {}}
    out = merge_skill_aggregate(base, rows, query_id="cross_selling", settings=Settings())
    assert "skill_aggregate" in out
    assert out["skill_aggregate"]["top_pairs"][0]["receita_combo"] == 100.0


def test_merge_skips_unknown_query_id():
    base = {"row_count": 0}
    out = merge_skill_aggregate(dict(base), [], query_id="ticket_medio_concessionaria_agg")
    assert "skill_aggregate" not in out


def test_merge_shrink_when_budget_tiny():
    rows = [
        {
            "servico_A_id": i,
            "servico_B_id": i + 1,
            "frequencia_combo": 1,
            "receita_combo": float(i),
        }
        for i in range(1, 40, 2)
    ]
    base = {}
    settings = Settings(llm_prompt_token_budget=50)
    out = merge_skill_aggregate(base, rows, query_id="cross_selling", settings=settings)
    assert out.get("skill_aggregate_json_truncated") is True
    assert len(out["skill_aggregate"]["top_pairs"]) < 20

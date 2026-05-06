from orion_mcp_v2.config.settings import Settings
from orion_mcp_v2.core.data_engine.pipeline import run_data_pipeline


def test_pipeline_basic():
    rows = [{"valor": 10.0, "nome": "A"}, {"valor": 20.0, "nome": "B"}]
    out = run_data_pipeline(rows)
    assert out["row_count"] == 2
    assert out["insights"]


def test_pipeline_cross_selling_skill_aggregate():
    rows = [
        {
            "servico_A_id": 1,
            "servico_B_id": 2,
            "frequencia_combo": 1,
            "receita_combo": 99.0,
        },
    ]
    out = run_data_pipeline(
        rows,
        query_id="cross_selling",
        intent="FATURAMENTO",
        settings=Settings(),
    )
    assert out["skill_aggregate"]["totals"]["receita_total"] == 99.0

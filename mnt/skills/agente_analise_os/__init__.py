"""
Pacote do agente de análise de OS (skill + gráficos + PDF).

Importação típica:
    from mnt.skills.agente_analise_os import gerar_todos_graficos, gerar_relatorio_pdf
    from mnt.skills.agente_analise_os.graficos import grafico_s1_resumo_executivo
    from mnt.skills.agente_analise_os.relatorio import gerar_relatorio_pdf
"""
from typing import TYPE_CHECKING

__all__ = [
    "gerar_todos_graficos",
    "grafico_s1_resumo_executivo",
    "grafico_s2_concessionarias",
    "grafico_s3_sazonalidade",
    "grafico_s4_produtos",
    "grafico_s5_vendedores",
    "grafico_s6_distribuicao_tickets",
    "grafico_s7_cross_selling",
    "grafico_s8_alertas",
    "gerar_relatorio_pdf",
]

if TYPE_CHECKING:
    from .graficos import (
        gerar_todos_graficos,
        grafico_s1_resumo_executivo,
        grafico_s2_concessionarias,
        grafico_s3_sazonalidade,
        grafico_s4_produtos,
        grafico_s5_vendedores,
        grafico_s6_distribuicao_tickets,
        grafico_s7_cross_selling,
        grafico_s8_alertas,
    )
    from .relatorio import gerar_relatorio_pdf


def __getattr__(name: str):
    if name in __all__:
        if name == "gerar_relatorio_pdf":
            from . import relatorio as _rel
            return getattr(_rel, name)
        from . import graficos as _graf
        return getattr(_graf, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

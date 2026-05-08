# app/services/graficos_cluster.py — delegação à skill (sem lógica de plot aqui)
from typing import Any, Dict


def gerar_graficos_cluster_resultado(
    resultado_maestro: Dict[str, Any],
    output_dir: str = "output/graficos_cluster",
) -> Dict[str, str]:
    """
    Gera PNGs a partir do retorno do Maestro quando há agente de clusterização.
    Implementação: `mnt.skills.agente_clusterizacao_concessionaria.graficos`.
    """
    from mnt.skills.agente_clusterizacao_concessionaria.graficos import (
        gerar_todos_graficos_cluster,
    )

    return gerar_todos_graficos_cluster(resultado_maestro, out_dir=output_dir)

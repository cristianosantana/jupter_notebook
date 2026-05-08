# app/services/maestro_service.py — Application Service que orquestra o fluxo Maestro
from typing import Any, Dict, List, Optional

from openai import OpenAI

from app.core.config import Settings, get_settings
from app.services.maestro_fluxo import executar_fluxo_maestro


class MaestroService:
    """Serviço de aplicação: executa o fluxo Maestro com dependências injetadas."""

    def __init__(
        self,
        client: OpenAI,
        settings: Optional[Settings] = None,
    ):
        self.client = client
        self.settings = settings or get_settings()

    def run(
        self,
        pergunta: str,
        agentes: Optional[List[str]] = None,
        agentes_dataframe: Optional[List[str]] = None,
        model: Optional[str] = None,
        verbose: bool = True,
        mysql_host: Optional[str] = None,
        mysql_porta: Optional[int] = None,
        mysql_usuario: Optional[str] = None,
        mysql_senha: Optional[str] = None,
        mysql_banco: Optional[str] = None,
        mysql_tabela: Optional[str] = None,
        mysql_tabelas: Optional[List[Dict]] = None,
        mysql_limite: int = 50000,
        mysql_filtro_where: str = "",
        mysql_injetar_namespace: Optional[Dict] = None,
        dataframe_preexistente: Optional[str] = None,
        skills_dir: Optional[str] = None,
        gerar_graficos_cluster_automatico: bool = True,
        graficos_cluster_output_dir: Optional[str] = None,
        invocar_visualizador_final: bool = True,
        **kwargs: Any,
    ) -> Dict:
        """Executa o fluxo Maestro e retorna o dict de resultado."""
        s = self.settings
        return executar_fluxo_maestro(
            self.client,
            pergunta=pergunta,
            model=model or s.modelo_default,
            agentes=agentes or [],
            agentes_dataframe=agentes_dataframe,
            verbose=verbose,
            mysql_host=mysql_host or s.mysql_host,
            mysql_porta=mysql_porta if mysql_porta is not None else s.mysql_port,
            mysql_usuario=mysql_usuario or s.mysql_user,
            mysql_senha=mysql_senha or s.mysql_password,
            mysql_banco=mysql_banco or s.mysql_database,
            mysql_tabela=mysql_tabela,
            mysql_tabelas=mysql_tabelas,
            mysql_limite=mysql_limite,
            mysql_filtro_where=mysql_filtro_where,
            mysql_injetar_namespace=mysql_injetar_namespace,
            dataframe_preexistente=dataframe_preexistente,
            skills_dir=skills_dir or s.skills_dir,
            gerar_graficos_cluster_automatico=gerar_graficos_cluster_automatico,
            graficos_cluster_output_dir=graficos_cluster_output_dir,
            invocar_visualizador_final=invocar_visualizador_final,
            **kwargs,
        )

    def gerar_graficos_cluster(
        self,
        resultado_maestro: Dict[str, Any],
        output_dir: str = "output/graficos_cluster",
    ) -> Dict[str, str]:
        """Delega à skill `agente_clusterizacao_concessionaria` (PNG a partir da resposta FASE 2 + specs)."""
        from app.services.graficos_cluster import gerar_graficos_cluster_resultado

        return gerar_graficos_cluster_resultado(resultado_maestro, output_dir=output_dir)

# app/services/relatorio_os_config.py — Preset de config e pós-processamento para relatório de OS
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd

logger = logging.getLogger("app.relatorio_os")

AGENTES_OS = ["agente_analise_os"]

MYSQL_TABELAS_OS = [
    {"tabela": "os", "alias": "os", "colunas": [
        "`os`.*",
        "EXISTS(SELECT 1 FROM caixas cx WHERE cx.os_id = os.id AND cx.cancelado = 0 "
        "AND cx.deleted_at IS NULL) AS os_paga",
        "(SELECT COUNT(*) FROM os_servicos oss2 WHERE oss2.os_id = os.id) AS qtd_servicos",
    ]},
    {"tabela": "os_servicos", "alias": "oss", "fk": "os.id = oss.os_id", "colunas": [
        "oss.id AS oss_id",
        "oss.codigo AS oss_codigo",
        "oss.valor_venda AS oss_valor_venda",
        "oss.valor_original AS oss_valor_original",
        "oss.desconto_supervisao AS oss_desconto_supervisao",
        "oss.desconto_migracao_cortesia AS oss_desconto_migracao_cortesia",
        "oss.desconto_avista AS oss_desconto_avista",
        "oss.valor_venda_real AS oss_valor_venda_real",
        "oss.desconto_bonus AS oss_desconto_bonus",
        "oss.fechado AS oss_fechado",
        "oss.cancelado AS oss_cancelado",
        "oss.servico_id AS oss_servico_id",
        "oss.os_tipo_id AS oss_os_tipo_id",
        "oss.combo_id AS oss_combo_id",
        "oss.concessionaria_execucao_id AS oss_concessionaria_execucao_id",
        "oss.created_at AS oss_created_at",
        "oss.deleted_at AS oss_deleted_at",
    ]},
    {"tabela": "servicos", "alias": "ser", "fk": "oss.servico_id = ser.id", "colunas": [
        "ser.id AS ser_id",
        "ser.nome AS servico_nome",
        "ser.custo_fixo AS ser_custo_fixo",
        "ser.grupo_servico_id AS ser_grupo_servico_id",
        "ser.subgrupo_servico_id AS ser_subgrupo_servico_id",
        "ser.servico_categoria_id AS ser_servico_categoria_id",
    ]},
    {"tabela": "concessionarias", "alias": "con", "fk": "os.concessionaria_id = con.id", "colunas": [
        "con.id AS con_id",
        "con.nome AS concessionaria_nome",
        "con.uf AS con_uf",
        "con.localidade AS con_localidade",
        "con.cluster_id AS con_cluster_id",
        "con.business_unit_id AS con_business_unit_id",
        "con.gerente_nome AS con_gerente_nome",
    ]},
    {"tabela": "funcionarios", "alias": "func", "fk": "os.vendedor_id = func.id", "colunas": [
        "func.id AS func_id",
        "func.nome AS vendedor_nome",
        "func.terceiros AS func_terceiros",
        "func.funcionario_situacao_id AS func_situacao_id",
    ]},
]

MYSQL_FILTRO_WHERE_OS = "os.deleted_at IS NULL AND os.created_at >= '{data_inicio}'"

PERGUNTA_OS = "Análise semanal completa de Ordens de Serviço"

_COLUNAS_DATETIME = ["created_at", "updated_at", "oss_created_at"]


def _normalizar_datas(df: pd.DataFrame) -> pd.DataFrame:
    for col in _COLUNAS_DATETIME:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce").dt.tz_localize(None)
    return df


def _extrair_analise(resultado: Dict[str, Any]) -> Dict[str, Any]:
    """Extrai o dict de análise (FASE 2) do resultado do Maestro."""
    respostas = resultado.get("respostas_agentes", [])
    if not respostas:
        return {}
    resp_agente = respostas[0]
    analise = resp_agente.get("resposta", {})
    if isinstance(analise, str):
        try:
            analise = json.loads(analise)
        except json.JSONDecodeError:
            analise = {"S1_resumo_executivo": analise, "S1_alerta": "normal"}
    return analise


def _extrair_metricas_execucao(resultado: Dict[str, Any]) -> Dict[str, int]:
    respostas = resultado.get("respostas_agentes", [])
    if not respostas:
        return {"metricas_sucesso": 0, "metricas_erro": 0}
    resumo = respostas[0].get("resultado_execucao", {}).get("resumo_execucao", {})
    return {
        "metricas_sucesso": resumo.get("metricas_sucesso", 0),
        "metricas_erro": resumo.get("metricas_erro", 0),
    }


def pos_processar_relatorio(
    resultado: Dict[str, Any],
    namespace: Dict[str, Any],
    output_dir: str = "output",
    gerar_pdf: bool = True,
) -> Dict[str, Any]:
    """
    Pós-processamento do resultado do Maestro:
      1. Recupera DataFrame do namespace e normaliza datas
      2. Extrai análise (FASE 2) do resultado
      3. Gera 8 gráficos PNG
      4. Gera PDF de 12 páginas (opcional)
      5. Salva análise JSON
      6. Retorna dict com paths dos arquivos gerados

    Args:
        resultado: Dict retornado por MaestroService.run() / executar_fluxo_maestro()
        namespace: Dict onde o DataFrame foi injetado (mysql_injetar_namespace)
        output_dir: Diretório base de saída
        gerar_pdf: Se True, gera o PDF além dos gráficos

    Returns:
        Dict com chaves: analise, graficos, pdf_path, analise_json_path, df_shape, metricas
    """
    from mnt.skills.agente_analise_os.graficos import gerar_todos_graficos
    from mnt.skills.agente_analise_os.relatorio import gerar_relatorio_pdf

    out = Path(output_dir)
    graficos_dir = out / "graficos"
    out.mkdir(parents=True, exist_ok=True)
    graficos_dir.mkdir(parents=True, exist_ok=True)

    # 1. Recuperar e normalizar DataFrame
    df_var = resultado.get("df_variavel")
    df = namespace.get(df_var) if df_var else None
    if df is None:
        raise RuntimeError(f"DataFrame '{df_var}' não encontrado no namespace.")
    df = _normalizar_datas(df)
    logger.info("DataFrame: %d linhas × %d colunas", df.shape[0], df.shape[1])

    # 2. Extrair análise
    analise = _extrair_analise(resultado)
    metricas = _extrair_metricas_execucao(resultado)

    # 3. Salvar análise JSON
    analise_json_path = str(out / "analise_agente.json")
    with open(analise_json_path, "w", encoding="utf-8") as f:
        json.dump(analise, f, ensure_ascii=False, indent=2)

    # 4. Gerar gráficos
    graficos = gerar_todos_graficos(df, str(graficos_dir))
    logger.info("%d gráficos gerados", len(graficos))

    # 5. Gerar PDF
    pdf_path: Optional[str] = None
    if gerar_pdf:
        hoje = datetime.now()
        semana_inicio = (hoje - timedelta(days=hoje.weekday())).strftime("%d/%m/%Y")
        semana_fim = hoje.strftime("%d/%m/%Y")
        periodo = f"{semana_inicio} a {semana_fim}"

        pdf_name = f"relatorio_semanal_os_{hoje.strftime('%Y%m%d')}.pdf"
        pdf_path = gerar_relatorio_pdf(
            analise=analise,
            graficos=graficos,
            out_path=str(out / pdf_name),
            titulo="Relatório Semanal de Ordens de Serviço",
            subtitulo="Análise Gerencial Automatizada",
            periodo=periodo,
        )
        logger.info("PDF gerado: %s", pdf_path)

    return {
        "analise": analise,
        "graficos": graficos,
        "pdf_path": pdf_path,
        "analise_json_path": analise_json_path,
        "df_shape": list(df.shape),
        "metricas": metricas,
        "entrega_final": resultado.get("entrega_final", ""),
    }

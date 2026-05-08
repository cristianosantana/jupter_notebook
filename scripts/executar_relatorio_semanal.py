#!/usr/bin/env python3
"""
Script CLI para execução do relatório semanal de OS.

Usa o mesmo MaestroService.run() que a API, com o preset de configuração
centralizado em app/services/relatorio_os_config.py.

Uso:
  python executar_relatorio_semanal.py
  python executar_relatorio_semanal.py --output-dir /caminho/personalizado
  python executar_relatorio_semanal.py --limite 100000

Para agendar via cron (toda segunda às 7h):
  0 7 * * 1 cd /home/lenovo/code/jupter_notebook && python executar_relatorio_semanal.py >> output/cron.log 2>&1
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.core.config import get_settings
from app.services.maestro_service import MaestroService
from app.services.relatorio_os_config import (
    AGENTES_OS,
    MYSQL_FILTRO_WHERE_OS,
    MYSQL_TABELAS_OS,
    PERGUNTA_OS,
    pos_processar_relatorio,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Relatório semanal de OS")
    parser.add_argument("--output-dir", default="output", help="Diretório de saída")
    parser.add_argument("--limite", type=int, default=50000, help="Limite de registros MySQL")
    parser.add_argument("--model", default=None, help="Modelo OpenAI (default: env OPENAI_MODEL ou gpt-5-mini)")
    parser.add_argument("--verbose", action="store_true", default=True, help="Logs detalhados")
    parser.add_argument("--no-pdf", action="store_true", help="Gerar apenas gráficos, sem PDF")
    parser.add_argument("--data-inicio", default="2023-01-01", help="Data mínima de os.created_at (YYYY-MM-DD)")
    return parser.parse_args()


def main():
    args = parse_args()
    t0 = time.time()

    load_dotenv()

    from openai import OpenAI

    settings = get_settings()
    client = OpenAI(api_key=settings.openai_api_key or None)
    maestro = MaestroService(client=client, settings=settings)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    model = args.model or settings.modelo_default

    print(f"[{datetime.now():%H:%M:%S}] Iniciando relatório semanal de OS...")
    print(f"  Modelo: {model}")
    print(f"  Limite MySQL: {args.limite}")
    print(f"  Data início: {args.data_inicio}")
    print(f"  Output: {output_dir.resolve()}")
    print()

    # === ETAPA 1: Executar fluxo Maestro (MySQL + FASE 1 + FASE 2) ===
    print(f"[{datetime.now():%H:%M:%S}] Executando fluxo Maestro...")
    namespace = {}
    resultado = maestro.run(
        pergunta=PERGUNTA_OS,
        agentes=AGENTES_OS,
        agentes_dataframe=AGENTES_OS,
        model=model,
        mysql_tabelas=MYSQL_TABELAS_OS,
        mysql_limite=args.limite,
        mysql_filtro_where=MYSQL_FILTRO_WHERE_OS.format(data_inicio=args.data_inicio),
        mysql_injetar_namespace=namespace,
        verbose=args.verbose,
    )

    # === ETAPA 2: Pós-processamento (gráficos + PDF) ===
    print(f"[{datetime.now():%H:%M:%S}] Pós-processamento...")
    arquivos = pos_processar_relatorio(
        resultado=resultado,
        namespace=namespace,
        output_dir=str(output_dir),
        gerar_pdf=not args.no_pdf,
    )

    # === Resumo ===
    metricas = arquivos.get("metricas", {})
    print(f"\n[{datetime.now():%H:%M:%S}] Métricas: "
          f"{metricas.get('metricas_sucesso', 0)} sucesso / "
          f"{metricas.get('metricas_erro', 0)} erro")

    print(f"  DataFrame: {arquivos['df_shape'][0]} linhas × {arquivos['df_shape'][1]} colunas")
    print(f"  Gráficos: {len(arquivos['graficos'])} PNGs")
    for secao, caminho in arquivos["graficos"].items():
        print(f"    {secao}: {caminho}")

    if arquivos.get("pdf_path"):
        print(f"  PDF: {arquivos['pdf_path']}")
    print(f"  Análise JSON: {arquivos['analise_json_path']}")

    elapsed = time.time() - t0
    print(f"\n[{datetime.now():%H:%M:%S}] Concluído em {elapsed:.1f}s")
    print(f"  Arquivos em: {output_dir.resolve()}")


if __name__ == "__main__":
    main()

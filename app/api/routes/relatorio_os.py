# app/api/routes/relatorio_os.py
import os
import time

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from app.api.schemas.relatorio_os import RelatorioOSRequest, RelatorioOSResponse
from app.core.deps import get_maestro_service
from app.services.maestro_service import MaestroService
from app.services.relatorio_os_config import (
    AGENTES_OS,
    MYSQL_FILTRO_WHERE_OS,
    MYSQL_TABELAS_OS,
    PERGUNTA_OS,
    pos_processar_relatorio,
)

router = APIRouter(tags=["relatorio-os"])

OUTPUT_DIR = os.environ.get("RELATORIO_OS_OUTPUT_DIR", "output")


@router.post("/relatorio-os", response_model=RelatorioOSResponse)
def post_relatorio_os(
    body: RelatorioOSRequest,
    maestro: MaestroService = Depends(get_maestro_service),
):
    """Executa o fluxo Maestro com agente_analise_os e gera gráficos + PDF."""
    t0 = time.time()
    namespace = {}

    resultado = maestro.run(
        pergunta=PERGUNTA_OS,
        agentes=AGENTES_OS,
        agentes_dataframe=AGENTES_OS,
        mysql_tabelas=MYSQL_TABELAS_OS,
        mysql_limite=body.limite,
        mysql_filtro_where=MYSQL_FILTRO_WHERE_OS.format(data_inicio=body.data_inicio),
        mysql_injetar_namespace=namespace,
        verbose=body.verbose,
    )

    arquivos = pos_processar_relatorio(
        resultado=resultado,
        namespace=namespace,
        output_dir=OUTPUT_DIR,
        gerar_pdf=body.gerar_pdf,
    )

    elapsed = time.time() - t0
    metricas = arquivos.get("metricas", {})

    return RelatorioOSResponse(
        analise=arquivos["analise"],
        graficos=arquivos["graficos"],
        pdf_path=arquivos.get("pdf_path"),
        entrega_final=arquivos.get("entrega_final", ""),
        metricas_sucesso=metricas.get("metricas_sucesso", 0),
        metricas_erro=metricas.get("metricas_erro", 0),
        df_shape=arquivos.get("df_shape", []),
        tempo_segundos=round(elapsed, 2),
    )


@router.get("/relatorio-os/download/{filename}")
def download_relatorio(filename: str):
    """Download de um arquivo gerado (PDF ou PNG)."""
    if ".." in filename or "/" in filename:
        raise HTTPException(status_code=400, detail="Nome de arquivo inválido")

    for subdir in ["", "graficos"]:
        path = os.path.join(OUTPUT_DIR, subdir, filename)
        if os.path.isfile(path):
            media = "application/pdf" if filename.endswith(".pdf") else "image/png"
            return FileResponse(path, media_type=media, filename=filename)

    raise HTTPException(status_code=404, detail=f"Arquivo '{filename}' não encontrado")

# app/api/schemas/relatorio_os.py
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class RelatorioOSRequest(BaseModel):
    """Corpo do POST /relatorio-os."""

    data_inicio: str = Field(
        default="2023-01-01",
        description="Data mínima de os.created_at (YYYY-MM-DD)",
    )
    limite: int = Field(default=50000, description="Limite de registros MySQL")
    gerar_pdf: bool = Field(default=True, description="Gerar PDF além dos gráficos")
    verbose: bool = True


class RelatorioOSResponse(BaseModel):
    """Resposta do POST /relatorio-os."""

    analise: Dict[str, Any] = Field(default_factory=dict, description="Análise FASE 2 do agente (8 seções)")
    graficos: Dict[str, str] = Field(default_factory=dict, description="Mapa seção → caminho PNG")
    pdf_path: Optional[str] = Field(default=None, description="Caminho do PDF gerado")
    entrega_final: str = ""
    metricas_sucesso: int = 0
    metricas_erro: int = 0
    df_shape: List[int] = Field(default_factory=list, description="[linhas, colunas] do DataFrame")
    tempo_segundos: float = 0.0

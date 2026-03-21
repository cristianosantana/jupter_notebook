# app/api/schemas/pergunta.py
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class PerguntaRequest(BaseModel):
    """Corpo do POST /pergunta."""

    pergunta: str = Field(..., min_length=1, description="Pergunta para o Maestro")
    agentes: Optional[List[str]] = None
    agentes_dataframe: Optional[List[str]] = Field(
        default=None,
        description="Skill IDs que operam em modo 2 fases com DataFrame (ex.: agente_analise_os)",
    )
    mysql_tabela: Optional[str] = None
    mysql_tabelas: Optional[List[Dict[str, Any]]] = None
    mysql_limite: int = 50000
    mysql_filtro_where: str = ""
    dataframe_preexistente: Optional[str] = Field(
        default=None,
        description=(
            "Nome da variável do DataFrame já registrada em memória no processo "
            "(ver app.services.maestro_df_registry). Se definido, o Maestro não consulta o MySQL para montar "
            "o contexto; mysql_tabelas/mysql_tabela têm prioridade se também forem enviados."
        ),
    )
    verbose: bool = True


class PerguntaResponse(BaseModel):
    """Resposta do POST /pergunta."""

    analise: Optional[Dict[str, Any]] = None
    respostas_agentes: List[Dict[str, Any]] = Field(default_factory=list)
    avaliacao: Optional[Dict[str, Any]] = None
    entrega_final: str = ""

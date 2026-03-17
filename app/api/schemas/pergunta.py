# app/api/schemas/pergunta.py
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class PerguntaRequest(BaseModel):
    """Corpo do POST /pergunta."""

    pergunta: str = Field(..., min_length=1, description="Pergunta para o Maestro")
    agentes: Optional[List[str]] = None
    mysql_tabela: Optional[str] = None
    mysql_tabelas: Optional[List[Dict[str, Any]]] = None
    mysql_limite: int = 50000
    mysql_filtro_where: str = ""
    verbose: bool = True


class PerguntaResponse(BaseModel):
    """Resposta do POST /pergunta."""

    analise: Optional[Dict[str, Any]] = None
    respostas_agentes: List[Dict[str, Any]] = Field(default_factory=list)
    avaliacao: Optional[Dict[str, Any]] = None
    entrega_final: str = ""

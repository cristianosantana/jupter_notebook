# app/api/routes/pergunta.py
from fastapi import APIRouter, Depends

from app.api.schemas.pergunta import PerguntaRequest, PerguntaResponse
from app.core.deps import get_maestro_service
from app.services.maestro_service import MaestroService

router = APIRouter(tags=["pergunta"])


@router.post("/pergunta", response_model=PerguntaResponse)
def post_pergunta(
    body: PerguntaRequest,
    maestro: MaestroService = Depends(get_maestro_service),
):
    """Executa o fluxo Maestro para a pergunta enviada."""
    resultado = maestro.run(
        pergunta=body.pergunta,
        agentes=body.agentes,
        mysql_tabela=body.mysql_tabela,
        mysql_tabelas=body.mysql_tabelas,
        mysql_limite=body.mysql_limite,
        mysql_filtro_where=body.mysql_filtro_where or "",
        verbose=body.verbose,
    )
    return PerguntaResponse(
        analise=resultado.get("analise"),
        respostas_agentes=resultado.get("respostas_agentes", []),
        avaliacao=resultado.get("avaliacao"),
        entrega_final=resultado.get("entrega_final", ""),
    )

# app/api/routes/pergunta.py
from fastapi import APIRouter, Depends, HTTPException

from app.api.schemas.pergunta import PerguntaRequest, PerguntaResponse
from app.core.deps import get_maestro_service
from app.services.maestro_df_registry import get_namespace
from app.services.maestro_service import MaestroService

router = APIRouter(tags=["pergunta"])


@router.post("/pergunta", response_model=PerguntaResponse)
def post_pergunta(
    body: PerguntaRequest,
    maestro: MaestroService = Depends(get_maestro_service),
):
    """Executa o fluxo Maestro para a pergunta enviada."""
    ns = None
    if body.dataframe_preexistente:
        ns = get_namespace()
        if body.dataframe_preexistente not in ns:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"DataFrame '{body.dataframe_preexistente}' não está registrado no processo. "
                    "Use maestro_df_registry.register('{nome}', df) no servidor antes de chamar /pergunta."
                ),
            )

    resultado = maestro.run(
        pergunta=body.pergunta,
        agentes=body.agentes,
        agentes_dataframe=body.agentes_dataframe,
        mysql_tabela=body.mysql_tabela,
        mysql_tabelas=body.mysql_tabelas,
        mysql_limite=body.mysql_limite,
        mysql_filtro_where=body.mysql_filtro_where or "",
        mysql_injetar_namespace=ns,
        dataframe_preexistente=body.dataframe_preexistente,
        verbose=body.verbose,
    )
    return PerguntaResponse(
        analise=resultado.get("analise"),
        respostas_agentes=resultado.get("respostas_agentes", []),
        avaliacao=resultado.get("avaliacao"),
        entrega_final=resultado.get("entrega_final", ""),
    )

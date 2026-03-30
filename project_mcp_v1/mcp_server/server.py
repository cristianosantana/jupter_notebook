from pathlib import Path
import sys

_mcp_root = Path(__file__).resolve().parent
if str(_mcp_root) not in sys.path:
    sys.path.insert(0, str(_mcp_root))

import json

from datetime import datetime
from typing import Literal

from mcp import types as mcp_types  # pyright: ignore[reportMissingImports]
from mcp.server.fastmcp import Context, FastMCP  # pyright: ignore[reportMissingImports]

import analytics_queries
import db
import sql_params

mcp = FastMCP(
    "ProductivityMCP",
    log_level="ERROR",
)

QueryId = Literal[
    "cross_selling",
    "taxa_retrabalho_servico_produtivo_concessionaria",
    "taxa_conversao_servico_concessionaria_vendedor",
    "servicos_vendidos_por_concessionaria",
    "sazonalidade_por_concessionaria",
    "performance_vendedor_periodo",
    "faturamento_ticket_concessionaria_periodo",
    "distribuicao_ticket_percentil",
    "propenso_compra_hora_dia_servico",
]


@mcp.tool(
    name="get_current_time",
    description="Data e hora atuais do servidor (ISO 8601).",
)
def get_current_time() -> str:
    return datetime.now().isoformat()


@mcp.resource(
    "analytics://query/{query_id}",
    name="analytics_query_sql",
    description="Texto SQL completo da análise (agregações definidas no servidor).",
)
def analytics_query_sql(query_id: str) -> str:
    return analytics_queries.get_sql(query_id)


@mcp.tool(
    name="list_analytics_queries",
    description=(
        "Lista todas as análises disponíveis com query_id, quando usar cada uma e URI do recurso MCP. "
        "Chame quando não tiver certeza qual query_id passar a run_analytics_query."
    ),
)
def list_analytics_queries() -> str:
    return analytics_queries.format_catalog_for_model()


_RUN_ANALYTICS_DESC = (
    "Executa uma análise pré-definida sobre OS/concessionárias/vendedores/serviços. "
    "Dados já vêm agregados no SQL; devolve no máximo 10000 linhas por chamada. "
    "Use offset para paginar. Para faturamento_ticket_concessionaria_periodo passe date_from e date_to (YYYY-MM-DD). summarize=true pede resumo via MCP Sampling (requer cliente com sampling). "
    "\n\n"
    + analytics_queries.QUERY_ID_PARAM_HELP
)


@mcp.tool(
    name="run_analytics_query",
    description=_RUN_ANALYTICS_DESC,
)
async def run_analytics_query(
    query_id: QueryId,
    limit: int = 10000,
    offset: int = 0,
    summarize: bool = False,
    date_from: str | None = None,
    date_to: str | None = None,
    ctx: Context | None = None,
) -> str:
    lim = max(1, min(10000, int(limit)))
    off = max(0, int(offset))

    try:
        sql_raw = analytics_queries.get_sql(query_id)
        sql_inner = sql_params.apply_placeholders(
            sql_raw,
            date_from=date_from,
            date_to=date_to,
        )
    except (KeyError, ValueError, OSError) as e:
        return json.dumps({"error": str(e), "query_id": query_id}, ensure_ascii=False)

    try:
        rows, _ = await db.run_wrapped_select(sql_inner, limit=lim, offset=off)
    except Exception as e:
        return json.dumps(
            {"error": "execução MySQL falhou", "detail": str(e)[:500]},
            ensure_ascii=False,
        )

    summarized: str | None = None
    if summarize and ctx is not None:
        preview = db.rows_to_json_payload(
            rows, query_id=query_id, limit=lim, offset=off, summarized=None
        )
        if len(preview) > 12000:
            preview = preview[:12000] + "…"
        try:
            msg = await ctx.session.create_message(
                messages=[
                    mcp_types.SamplingMessage(
                        role="user",
                        content=mcp_types.TextContent(
                            type="text",
                            text=(
                                "Resuma em português (até 8 bullets curtos) os principais insights. "
                                "Não invente números fora dos dados.\n\n"
                                + preview
                            ),
                        ),
                    )
                ],
                max_tokens=600,
                system_prompt="Analista de dados conciso. Responde só com bullets.",
            )
            if isinstance(msg, mcp_types.CreateMessageResult):
                summarized = msg.content.text
            elif isinstance(msg, mcp_types.ErrorData):
                summarized = None
        except Exception:
            summarized = None

    return db.rows_to_json_payload(
        rows, query_id=query_id, limit=lim, offset=off, summarized=summarized
    )


if __name__ == "__main__":
    mcp.run()

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
from trace_logging import meta_run_id, trace_record

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
    "performance_vendedor_mes",
    "performance_vendedor_ano",
    "faturamento_ticket_concessionaria_periodo",
    "distribuicao_ticket_percentil",
    "propenso_compra_hora_dia_servico",
    "volume_os_concessionaria_mom",
    "volume_os_vendedor_ranking",
    "ticket_medio_concessionaria_agg",
    "ticket_medio_vendedor_top_bottom",
    "taxa_conversao_servicos_os_fechada",
]


def _trace_rid(ctx: Context | None) -> str | None:
    if ctx is None:
        return None
    try:
        return meta_run_id(ctx.request_context.meta)
    except Exception:
        return None


@mcp.tool(
    name="get_current_time",
    description="Data e hora atuais do servidor (ISO 8601).",
)
def get_current_time(ctx: Context) -> str:
    rid = _trace_rid(ctx)
    trace_record("mcp.server.tool.start", run_id=rid, tool="get_current_time")
    out = datetime.now().isoformat()
    trace_record("mcp.server.tool.end", run_id=rid, tool="get_current_time", result=out)
    return out


@mcp.resource(
    "analytics://query/{query_id}",
    name="analytics_query_sql",
    description=(
        "SQL completo da análise (agregações no servidor). Inclui filtros de período "
        "__MCP_DATE_FROM__ e __MCP_DATE_TO__; ao executar, passe date_from e date_to em run_analytics_query."
    ),
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
def list_analytics_queries(ctx: Context) -> str:
    rid = _trace_rid(ctx)
    trace_record("mcp.server.tool.start", run_id=rid, tool="list_analytics_queries")
    out = analytics_queries.format_catalog_for_model()
    trace_record(
        "mcp.server.tool.end",
        run_id=rid,
        tool="list_analytics_queries",
        result_chars=len(out),
        result_preview=out[:4000],
    )
    return out


_RUN_ANALYTICS_DESC = (
    "Executa uma análise pré-definida sobre OS/concessionárias/vendedores/serviços. "
    "Dados já vêm agregados no SQL; devolve no máximo 10000 linhas por chamada. "
    "Use offset para paginar. "
    "Para qualquer query_id são obrigatórios date_from e date_to (YYYY-MM-DD), alinhados aos placeholders do recurso analytics://query/{query_id}. "
    "As análises tabulares clássicas (cross_selling até propenso_compra_hora_dia_servico) devolvem sempre "
    "JSON compacto (rows_sample + llm_summary se o sampling MCP existir), mesmo com summarize=false — não há envio do dataset completo ao cliente LLM. "
    "Para os restantes query_id, summarize=true pede o mesmo formato compacto; summarize=false devolve todas as linhas da página (até limit). "
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
    rid = _trace_rid(ctx)
    trace_record(
        "mcp.server.tool.start",
        run_id=rid,
        tool="run_analytics_query",
        query_id=query_id,
        limit=lim,
        offset=off,
        summarize=summarize,
        date_from=date_from,
        date_to=date_to,
    )

    try:
        sql_raw = analytics_queries.get_sql(query_id)
        sql_inner = sql_params.apply_placeholders(
            sql_raw,
            date_from=date_from,
            date_to=date_to,
        )
    except (KeyError, ValueError, OSError) as e:
        result = json.dumps({"error": str(e), "query_id": query_id}, ensure_ascii=False)
    else:
        try:
            rows, _ = await db.run_wrapped_select(sql_inner, limit=lim, offset=off)
        except Exception as e:
            result = json.dumps(
                {"error": "execução MySQL falhou", "detail": str(e)[:500]},
                ensure_ascii=False,
            )
        else:
            effective_compact = summarize or (
                query_id in analytics_queries.TABULAR_LEGACY_QUERY_IDS
            )

            summarized: str | None = None
            if effective_compact and ctx is not None:
                preview = db.rows_to_sampling_preview_payload(
                    rows, query_id=query_id, sample_size=40
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

            if effective_compact:
                result = db.rows_to_compact_json_payload(
                    rows,
                    query_id=query_id,
                    limit=lim,
                    offset=off,
                    summarized=summarized,
                )
            else:
                result = db.rows_to_json_payload(
                    rows,
                    query_id=query_id,
                    limit=lim,
                    offset=off,
                    summarized=summarized,
                )

    trace_record(
        "mcp.server.tool.end",
        run_id=rid,
        tool="run_analytics_query",
        query_id=query_id,
        result_preview=result[:8000],
        result_chars=len(result),
    )
    return result


if __name__ == "__main__":
    mcp.run()

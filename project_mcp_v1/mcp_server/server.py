"""
Servidor MCP (FastMCP): tempo, catálogo de análises SQL, execução de queries
agregadas e glossário de entidades para o orquestrador da API.
"""
from pathlib import Path
import sys

# Raiz do pacote mcp_server (para imports locais: db, analytics_queries, …)
_mcp_root = Path(__file__).resolve().parent
if str(_mcp_root) not in sys.path:
    sys.path.insert(0, str(_mcp_root))
# Raiz do repositório (para importar app.config / app.entity_glossary no glossário)
_proj_root = _mcp_root.parent
if str(_proj_root) not in sys.path:
    sys.path.append(str(_proj_root))

import json

from datetime import datetime

from mcp import types as mcp_types  # pyright: ignore[reportMissingImports]
from mcp.server.fastmcp import Context, FastMCP  # pyright: ignore[reportMissingImports]

import analytics_queries
import db
import sql_params
from serpapi_search import google_search_serpapi as _google_search_serpapi
from serpapi_search import serpapi_enabled as _serpapi_enabled
from trace_logging import meta_run_id, trace_record

# Instância principal FastMCP exposta ao cliente (stdio)
mcp = FastMCP(
    "ProductivityMCP",
    log_level="ERROR",
)


def _trace_rid(ctx: Context | None) -> str | None:
    """Extrai o run_id de trace (agent_trace_run_id) do meta do pedido MCP, se existir."""
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
    """Tool: devolve data/hora do servidor em ISO 8601 (útil para referência temporal)."""
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
    """Recurso MCP: texto SQL bruto da análise identificada por ``query_id``."""
    return analytics_queries.get_sql(query_id)


@mcp.tool(
    name="list_analytics_queries",
    description=(
        "Lista todas as análises disponíveis com query_id, quando usar cada uma e URI do recurso MCP. "
        "Chame quando não tiver certeza qual query_id passar a run_analytics_query."
    ),
)
def list_analytics_queries(ctx: Context) -> str:
    """Tool: catálogo formatado para o modelo (ids, descrições, URIs das queries)."""
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


# Texto longo da descrição da tool run_analytics_query (reutilizado no decorator)
_RUN_ANALYTICS_DESC = (
    "Executa uma análise pré-definida sobre OS/concessionárias/vendedores/serviços. "
    "Dados já vêm agregados no SQL; devolve no máximo 10000 linhas por chamada. "
    "Use offset para paginar. "
    "Para qualquer query_id são obrigatórios date_from e date_to (YYYY-MM-DD), alinhados aos placeholders do recurso analytics://query/{query_id}. "
    "Com summarize=false o JSON inclui o campo rows com todas as linhas desta página (até limit) para qualquer análise tabular multi-linha; "
    "análises com resultado JSON agregado (coluna resultado) também devolvem essas linhas em rows. "
    "Com summarize=true a resposta fica compacta (rows_sample, notas e llm_summary se o sampling MCP existir). "
    "\n\n"
    + analytics_queries.QUERY_ID_PARAM_HELP
)


@mcp.tool(
    name="run_analytics_query",
    description=_RUN_ANALYTICS_DESC,
)
async def run_analytics_query(
    query_id: str,
    limit: int = 10000,
    offset: int = 0,
    summarize: bool = False,
    date_from: str | None = None,
    date_to: str | None = None,
    ctx: Context | None = None,
) -> str:
    """
    Tool: executa SQL da análise no MySQL, com paginação e opcional resumo via sampling MCP.

    - ``limit`` / ``offset``: janela de linhas (cap 10000).
    - ``summarize``: se True, pede resumo ao host via create_message (quando ``ctx`` existe).
    - ``date_from`` / ``date_to``: substituem placeholders no SQL.
    """
    lim = max(1, min(10000, int(limit)))  # limite de linhas por chamada (1..10000)
    off = max(0, int(offset))  # deslocamento para paginação
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

    if query_id not in analytics_queries.QUERY_REGISTRY:
        result = json.dumps(
            {
                "error": "query_id desconhecido",
                "query_id": query_id,
                "known_query_ids": list(analytics_queries.QUERY_IDS),
            },
            ensure_ascii=False,
        )
        trace_record(
            "mcp.server.tool.end",
            run_id=rid,
            tool="run_analytics_query",
            query_id=query_id,
            result_preview=result[:2000],
        )
        return result

    try:
        sql_raw = analytics_queries.get_sql(query_id)  # SQL com placeholders de data
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
            effective_compact = bool(summarize)  # modo resumido (payload compacto)

            summarized: str | None = None  # texto do LLM via sampling, se disponível
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


@mcp.tool(
    name="get_entity_glossary_markdown",
    description=(
        "Constrói o glossário de dimensões (MySQL) para o system prompt. "
        "O orquestrador da API chama esta tool para não abrir MySQL no processo uvicorn."
    ),
)
async def get_entity_glossary_markdown(
    max_chars: int | None = None,
    include_demais_registos: bool | None = None,
    ctx: Context | None = None,
) -> str:
    """
    Tool: gera markdown do glossário de entidades (concessionárias, serviços, etc.).

    Parâmetros opcionais sobrepõem temporariamente ``entity_glossary_*`` do Settings.
    Resposta: JSON com ``markdown`` e ``stats``, ou ``error`` em falha.
    """
    rid = _trace_rid(ctx)
    trace_record("mcp.server.tool.start", run_id=rid, tool="get_entity_glossary_markdown")
    try:
        from app.config import get_settings
        from app.entity_glossary import build_entity_glossary_markdown

        st = get_settings()
        updates: dict[str, object] = {}  # patches pontuais sobre a config carregada
        if max_chars is not None:
            updates["entity_glossary_max_chars"] = max(256, int(max_chars))
        if include_demais_registos is not None:
            updates["entity_glossary_include_demais_registos"] = bool(include_demais_registos)
        st_eff = st.model_copy(update=updates) if updates else st  # Settings efectivo para esta chamada

        markdown, stats = await build_entity_glossary_markdown(
            st_eff,
            run_wrapped_select=db.run_wrapped_select,
        )
        payload = json.dumps(
            {"markdown": markdown, "stats": stats},
            ensure_ascii=False,
            default=str,
        )
    except Exception as e:
        payload = json.dumps(
            {"error": str(e), "error_type": type(e).__name__},
            ensure_ascii=False,
        )

    trace_record(
        "mcp.server.tool.end",
        run_id=rid,
        tool="get_entity_glossary_markdown",
        result_preview=payload[:8000],
        result_chars=len(payload),
    )
    return payload


if _serpapi_enabled():

    @mcp.tool(
        name="google_search_serpapi",
        description=(
            "Pesquisa Google via SerpApi: contexto externo (notícias, definições públicas, concorrentes). "
            "Argumento search_query: texto como na caixa de pesquisa Google (frase curta ou keywords), "
            "inferido da pergunta do utilizador. Proibido usar query_id ou IDs de list_analytics_queries — "
            "isso é só para run_analytics_query. Obrigatório quando precisares de factos da web; "
            "não substitui run_analytics_query para métricas internas."
        ),
    )
    async def google_search_serpapi(
        search_query: str,
        num_results: int = 3,
        ctx: Context | None = None,
    ) -> str:
        """
        Devolve JSON com organic_results e answer_box resumidos.
        Usa search_query (web), nunca query_id de analytics.
        """
        rid = _trace_rid(ctx)
        trace_record(
            "mcp.server.tool.start",
            run_id=rid,
            tool="google_search_serpapi",
            search_query=search_query,
        )
        out = await _google_search_serpapi(search_query, num_results=num_results)
        trace_record(
            "mcp.server.tool.end",
            run_id=rid,
            tool="google_search_serpapi",
            result_preview=out[:4000],
            result_chars=len(out),
        )
        return out


if __name__ == "__main__":
    # Arranque em modo stdio (subprocesso ligado pelo cliente MCP da API)
    mcp.run()

"""Catálogo de análises SQL (ficheiros em query_sql/). Metadados no cabeçalho YAML de cada .sql."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Final

from query_sql_meta import parse_sql_file

QUERY_DIR: Final[Path] = Path(__file__).resolve().parent / "query_sql"


def _build_registry() -> tuple[dict[str, dict[str, Any]], frozenset[str]]:
    reg: dict[str, dict[str, Any]] = {}
    tabular: set[str] = set()
    paths = sorted(QUERY_DIR.glob("*.sql"), key=lambda p: p.name)
    if not paths:
        raise RuntimeError(f"nenhum ficheiro .sql em {QUERY_DIR}")

    for path in paths:
        meta, sql_core = parse_sql_file(path)
        qid = meta["query_id"]
        if qid in reg:
            raise RuntimeError(f"query_id duplicado: {qid}")
        if meta["output_shape"] == "tabular_multiline":
            tabular.add(qid)

        entry: dict[str, Any] = {
            "filename": path.name,
            "resource_description": meta["resource_description"],
            "when_to_use": meta["when_to_use"],
            "sql_body": sql_core,
        }
        if meta.get("not_confused_with"):
            entry["not_confused_with"] = list(meta["not_confused_with"])
        reg[qid] = entry

    return reg, frozenset(tabular)


QUERY_REGISTRY, TABULAR_MULTIROW_QUERY_IDS = _build_registry()

# Contexto inicial: domínio que o agente cobre para responder (catálogo + MCP + instruções ao modelo).
AGENT_ANALYTICS_DOMAIN_INTRO: Final[str] = (
    "Domínio do agente: análises sobre oficina/concessionária em MySQL — ordens de serviço (OS), "
    "serviços e linhas vendidas, faturamento e ticket, vendedores e concessionárias, descontos, "
    "volume e estado das OS (abertas/fechadas/canceladas), sazonalidade, mix de serviços, "
    "retrabalho, conversão de serviço/OS, cross-selling, faturamento mensal recebido vs pendente (caixas, global e por concessionária), "
    "distribuição de tickets (percentis) e "
    "propensão de compra por hora/dia. Só responde com base nas análises SQL catalogadas (query_id); "
    "o texto «quando usar» e descrições curtas vêm dos cabeçalhos YAML em mcp_server/query_sql/*.sql. "
    "Período sempre delimitado por date_from e date_to (YYYY-MM-DD). "
    "Fora deste catálogo não há execução automática de relatórios ad-hoc."
)

QUERY_IDS: tuple[str, ...] = tuple(sorted(QUERY_REGISTRY.keys()))

GLOBAL_PERIOD_HELP = (
    "Todas as análises filtram por intervalo de datas: em run_analytics_query são obrigatórios "
    "date_from e date_to (YYYY-MM-DD). O recurso MCP analytics://query/{query_id} mostra o SQL com "
    "os placeholders __MCP_DATE_FROM__ e __MCP_DATE_TO__. "
    "Para qualquer query_id: com summarize=false o JSON inclui o campo rows com todas as linhas retornadas "
    "nesta página (até limit; usar offset para paginar). Com summarize=true a resposta é compacta "
    "(rows_sample e opcionalmente llm_summary via sampling MCP)."
)

QUERY_ID_PARAM_HELP = (
    AGENT_ANALYTICS_DOMAIN_INTRO
    + "\n\n"
    + GLOBAL_PERIOD_HELP
    + "\n\nIdentificador da análise. Escolha conforme a intenção:\n"
    + "\n".join(
        f"- {qid}: {QUERY_REGISTRY[qid]['resource_description']} — {QUERY_REGISTRY[qid]['when_to_use']}"
        for qid in QUERY_IDS
    )
)


def get_sql(query_id: str) -> str:
    if query_id not in QUERY_REGISTRY:
        raise KeyError(f"query_id desconhecido: {query_id}")
    return str(QUERY_REGISTRY[query_id]["sql_body"])


def format_catalog_for_model() -> str:
    lines = [
        AGENT_ANALYTICS_DOMAIN_INTRO,
        "",
        "Catálogo de análises (use o query_id em run_analytics_query). "
        "SQL completo: recurso MCP analytics://query/{query_id}. "
        "Metadados editáveis no cabeçalho /* @mcp_query_meta ... */ de cada ficheiro em query_sql/.",
        "",
        GLOBAL_PERIOD_HELP,
        "",
    ]
    for qid in QUERY_IDS:
        meta = QUERY_REGISTRY[qid]
        lines.append(f"## {qid}")
        lines.append(f"- Descrição: {meta['resource_description']}")
        if qid in TABULAR_MULTIROW_QUERY_IDS:
            lines.append(
                "- Formato: tabular multi-linha no SQL; summarize=false devolve o campo rows com todas as linhas "
                "da página (até limit); summarize=true devolve formato compacto (rows_sample / resumo)."
            )
        else:
            lines.append(
                "- Formato: uma linha típica com coluna `resultado` (JSON agregado no MySQL)."
            )
        lines.append(f"- Quando usar: {meta['when_to_use']}")
        ncf = meta.get("not_confused_with")
        if isinstance(ncf, list) and ncf:
            lines.append(f"- Não confundir com: {', '.join(ncf)}")
        lines.append(f"- Recurso: analytics://query/{qid}")
        lines.append("")
    return "\n".join(lines).rstrip()

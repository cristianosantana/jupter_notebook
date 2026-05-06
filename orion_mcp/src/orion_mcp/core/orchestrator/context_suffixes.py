"""Sufixos determinísticos ao texto `user` do LLM após `build_context`."""

from __future__ import annotations

from orion_mcp.core.config.settings import Settings
from orion_mcp.core.state.models import State

_CATALOG_SNIPPET = "resultado de consulta catalogada"


def state_has_catalog_query_summary(state: State) -> bool:
    """True se algum resumo de tool for o formato de consulta catalogada (DataInterpreter)."""
    for entry in state.data_cache.values():
        if _CATALOG_SNIPPET in (entry.summary or "").lower():
            return True
    return False


def apply_chat_user_context_suffixes(
    ctx_text: str, state: State, *, settings: Settings | None = None
) -> str:
    """
    Acrescenta instruções internas antes de `cap_llm_prompt`.
    Mantém-se curto para reduzir risco de truncagem no fim do prompt.
    """
    t = ctx_text
    if state.intent == "why_question":
        t += (
            "\n### Instrução interna\n"
            "Explica causas prováveis de forma cautelosa, apenas com base nos dados resumidos.\n"
        )
    if state_has_catalog_query_summary(state):
        full_rows = bool(settings and settings.tool_llm_catalog_full_rows)
        if full_rows:
            t += (
                "\n### Instrução interna\n"
                "«Dados resumidos» incluem o conjunto **completo** de linhas tabulares devolvidas pela consulta "
                "nesta página (limite/offset da tool). Interpreta **só** esse bloco: podes agregar, rankear e "
                "calcular métricas sobre essas linhas; não inventes linhas que não apareçam. "
                "Não sugiras SQL, Pandas nem código para ir **buscar** dados fora deste bloco. "
                "Se `row_count` atingir o `limit` da consulta, pode haver mais páginas — indica paginação na API.\n"
            )
        else:
            t += (
                "\n### Instrução interna\n"
                "Já há resultado de consulta catalogada em «Dados resumidos» (pré-visualização e metadados). "
                "Interpreta **só** esse bloco: não sugiras SQL, Pandas nem código para “executar a agregação”. "
                "Se o pedido exigir ranking/top sobre todas as linhas e a pré-visualização for parcial, explica o "
                "limite (amostra, summarize, paginação) e indica opções de **novo pedido à API** sem escrever queries.\n"
            )
    return t

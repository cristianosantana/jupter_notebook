"""
Glossário de dimensões para o system prompt: concessionárias, pessoas por papel
(via ``funcionario_cargos`` + ``cargos.funcionario_tipo_id``), serviços.

O texto injectado no modelo é objectivo (secções Vendedores / Produtivos / Supervisores);
não repete narrativa de RH. Ajustar ``_TIPO_*`` se os IDs de tipo mudarem na BD.

Filtros extra por tabela vêm de ``Settings`` (``.env``); por omissão vazios para schemas sem
``ativo``/``deleted_at``.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from app.config import Settings

# Servidor MCP injecta ``db.run_wrapped_select`` (MySQL só no subprocesso MCP).
RunWrappedSelect = Callable[..., Awaitable[tuple[list[dict[str, Any]], int | None]]]

# ``cargos.funcionario_tipo_id`` por papel (negócio).
_TIPO_VENDEDOR: tuple[int, ...] = (1,)
_TIPO_PRODUTIVO: tuple[int, ...] = (5, 7)
_TIPO_SUPERVISOR: tuple[int, ...] = (2,)

_PER_TABLE_LIMIT = 5000


def _sql_extra_fragment(raw: str) -> str:
    """Normaliza fragmento opcional `` AND col …``; vazio se não definido."""
    s = (raw or "").strip()
    if not s:
        return ""
    if s.upper().startswith("AND"):
        return " " + s
    return " AND " + s


def _all_mapped_funcionario_tipo_ids() -> tuple[int, ...]:
    return tuple(sorted(set(_TIPO_VENDEDOR + _TIPO_PRODUTIVO + _TIPO_SUPERVISOR)))


def _sample_ids(rows: list[dict[str, Any]], n: int = 5) -> list[Any]:
    return [r.get("id") for r in rows[:n]]


def _sql_in_ints(ids: tuple[int, ...]) -> str:
    return ",".join(str(i) for i in ids)


def _sql_personas_por_funcionario_tipo(tipos: tuple[int, ...], extra_fun: str) -> str:
    ins = _sql_in_ints(tipos)
    return (
        "SELECT DISTINCT fun.id, fun.nome FROM funcionarios AS fun "
        "INNER JOIN funcionario_cargos AS fun_c ON fun_c.funcionario_id = fun.id "
        "INNER JOIN cargos AS car ON fun_c.cargo_id = car.id "
        f"WHERE car.funcionario_tipo_id IN ({ins})"
        f"{extra_fun} ORDER BY fun.nome ASC"
    )


def _sql_demais_sem_tipos_mapeados(extra_fun: str) -> str:
    mapped = _all_mapped_funcionario_tipo_ids()
    ins = _sql_in_ints(mapped)
    return (
        "SELECT fun.id, fun.nome FROM funcionarios AS fun "
        "WHERE 1=1"
        f"{extra_fun} "
        "AND NOT EXISTS ("
        "SELECT 1 FROM funcionario_cargos AS fun_c "
        "INNER JOIN cargos AS car ON fun_c.cargo_id = car.id "
        f"WHERE fun_c.funcionario_id = fun.id AND car.funcionario_tipo_id IN ({ins})"
        ") ORDER BY fun.nome ASC"
    )


async def build_entity_glossary_markdown(
    settings: Settings,
    *,
    run_wrapped_select: RunWrappedSelect | None = None,
) -> tuple[str, dict[str, Any]]:
    """
    Carrega dimensões da BD e devolve (markdown truncado a ``entity_glossary_max_chars``, estatísticas).

    Com ``run_wrapped_select=None`` usa ``mcp_server.db`` no processo actual (uvicorn) — evitar; preferir
    tool MCP ``get_entity_glossary_markdown`` que passa ``db.run_wrapped_select``.
    """
    _run: RunWrappedSelect
    if run_wrapped_select is None:
        from mcp_server.db import run_wrapped_select as _run
    else:
        _run = run_wrapped_select

    max_chars = max(256, int(settings.entity_glossary_max_chars))
    extra_fun = _sql_extra_fragment(settings.entity_glossary_sql_fun_extra)
    extra_conc = _sql_extra_fragment(settings.entity_glossary_sql_concessionarias_extra)
    extra_serv = _sql_extra_fragment(settings.entity_glossary_sql_servicos_extra)

    async def _rows(sql: str) -> list[dict[str, Any]]:
        rows, _ = await _run(sql, limit=_PER_TABLE_LIMIT, offset=0)
        return rows

    sections: list[str] = [
        "## Glossário de dimensões (activas / listadas)",
        "",
        "Resolve ids nas secções abaixo conforme o **nome da coluna** nos dados "
        "(`concessionaria_id`, `vendedor_id`, `produtivo_id`, `supervisor_id`, `servico_id`, …).",
        "Se um id não tiver linha no glossário, indica que não consta do glossário actual — não inventes nome.",
        "",
    ]

    q_conc = (
        "SELECT id, nome FROM concessionarias WHERE 1=1"
        f"{extra_conc} ORDER BY nome ASC"
    )
    q_serv = (
        "SELECT id, nome FROM servicos WHERE 1=1"
        f"{extra_serv} ORDER BY nome ASC"
    )

    conc = await _rows(q_conc)
    sections.append("### Concessionárias (`concessionaria_id`)")
    sections.extend(f"- id={r['id']}: {r.get('nome', '')}" for r in conc)
    sections.append("")

    mode = "role_sections_join"
    v_rows = await _rows(_sql_personas_por_funcionario_tipo(_TIPO_VENDEDOR, extra_fun))
    sections.append("### Vendedores (`vendedor_id`)")
    sections.extend(f"- id={r['id']}: {r.get('nome', '')}" for r in v_rows)
    sections.append("")

    p_rows = await _rows(_sql_personas_por_funcionario_tipo(_TIPO_PRODUTIVO, extra_fun))
    sections.append("### Produtivos (`produtivo_id`)")
    sections.extend(f"- id={r['id']}: {r.get('nome', '')}" for r in p_rows)
    sections.append("")

    s_rows = await _rows(_sql_personas_por_funcionario_tipo(_TIPO_SUPERVISOR, extra_fun))
    sections.append("### Supervisores (`supervisor_id`)")
    sections.extend(f"- id={r['id']}: {r.get('nome', '')}" for r in s_rows)
    sections.append("")

    demais_rows: list[dict[str, Any]] = []
    if settings.entity_glossary_include_demais_registos:
        demais_rows = await _rows(_sql_demais_sem_tipos_mapeados(extra_fun))
        if demais_rows:
            sections.append(
                "### Demais registos (sem cargo mapeado a vendedor / produtivo / supervisor)"
            )
            sections.extend(f"- id={r['id']}: {r.get('nome', '')}" for r in demais_rows)
            sections.append("")

    serv = await _rows(q_serv)
    sections.append("### Serviços (`servico_id`)")
    sections.extend(f"- id={r['id']}: {r.get('nome', '')}" for r in serv)
    sections.append("")

    text = "\n".join(sections).strip()
    truncated = len(text) > max_chars
    if truncated:
        markdown = text[: max_chars - 80] + "\n\n[… glossário truncado por entity_glossary_max_chars …]"
    else:
        markdown = text

    stats: dict[str, Any] = {
        "concessionarias_count": len(conc),
        "servicos_count": len(serv),
        "glossary_personas_mode": mode,
        "markdown_chars_before_trunc": len(text),
        "markdown_chars": len(markdown),
        "truncated": truncated,
        "max_chars_limit": max_chars,
        "concessionarias_sample_ids": _sample_ids(conc),
        "servicos_sample_ids": _sample_ids(serv),
        "vendedores_section_count": len(v_rows),
        "produtivos_section_count": len(p_rows),
        "supervisores_section_count": len(s_rows),
        "demais_registros_count": len(demais_rows),
        "vendedores_sample_ids": _sample_ids(v_rows),
        "produtivos_sample_ids": _sample_ids(p_rows),
        "supervisores_sample_ids": _sample_ids(s_rows),
        "demais_sample_ids": _sample_ids(demais_rows),
        "distinct_cargo_sections": 0,
        "personas_total_rows_cargo_grouped": 0,
        "funcionario_tipo_ids_mapped": list(_all_mapped_funcionario_tipo_ids()),
    }
    return markdown, stats

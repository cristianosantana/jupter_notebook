from __future__ import annotations

import json
from typing import Any


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _format_row(row: dict[str, Any]) -> str:
    parts = [f"{k}={json.dumps(v, ensure_ascii=False)}" for k, v in row.items()]
    return "  " + " | ".join(parts)


def _joined_row_block_len(row_lines: list[str]) -> int:
    if not row_lines:
        return 0
    return sum(len(x) for x in row_lines) + (len(row_lines) - 1)


def _clip_by_lines(text: str, max_chars: int) -> str:
    """Remove linhas de dados do fim até caber em max_chars (nunca corta a meio de linha)."""
    if len(text) <= max_chars:
        return text
    lines = text.split("\n")
    if not lines:
        return text[:max_chars] + "…"
    out: list[str] = []
    for line in lines:
        candidate = "\n".join(out + [line]) if out else line
        if len(candidate) > max_chars:
            if not out and len(line) > max_chars:
                return line[: max_chars - 60] + "… [linha única truncada por teto]"
            omitted = len(lines) - len(out)
            out.append(f"… [{omitted} linhas omitidas por teto de caracteres após interpretação]")
            break
        out.append(line)
    return "\n".join(out)


def _summarize_drl_payload(result: dict[str, Any], *, max_chars: int) -> str:
    """Texto estável a partir de drl_summary / drl_insights / drl_sample (sem rows brutas)."""
    budget_s = min(8000, int(max_chars * 0.5))
    budget_i = min(2000, int(max_chars * 0.2))
    budget_a = max(256, max_chars - budget_s - budget_i - 400)
    qid = str(result.get("query_id") or "").strip()
    did = str(result.get("dataset_id") or "").strip()
    lines = [
        "### Resultado catalogado (DRL)",
        f"- query_id: {qid}",
        f"- dataset_id: {did or '(n/d)'}",
    ]
    drl_summary = result.get("drl_summary")
    lines.append("### drl_summary")
    js = json.dumps(drl_summary, ensure_ascii=False, default=str)
    if len(js) > budget_s:
        lines.append(js[: budget_s - 1] + "…")
    else:
        lines.append(js)
    ins = result.get("drl_insights") or []
    lines.append("### drl_insights")
    ins_txt = "\n".join(f"- {x}" for x in ins if isinstance(x, str))
    if len(ins_txt) > budget_i:
        lines.append(ins_txt[: budget_i - 1] + "…")
    else:
        lines.append(ins_txt or "(nenhum)")
    samp = result.get("drl_sample")
    lines.append("### drl_sample")
    j2 = json.dumps(samp, ensure_ascii=False, default=str)
    if len(j2) > budget_a:
        lines.append(j2[: budget_a - 1] + "…")
    else:
        lines.append(j2)
    return "\n".join(lines)


def tool_result_to_llm_summary(
    result: dict[str, Any],
    *,
    preview_rows: int = 10,
    max_chars: int = 12000,
    catalog_full_rows: bool = False,
) -> str:
    """
    Converte o dict devolvido por uma tool num texto estável para o LLM.
    Para resultados catalogados (SQL MCP / stub / degradação), evita json.dumps + corte bruto.
    """
    if not isinstance(result, dict):
        return str(result)[: max_chars - 30] + "…"

    if result.get("cached"):
        return str(result.get("cached_summary", ""))

    if result.get("mcp_degraded"):
        note = str(result.get("note") or "mcp_degraded")
        err = result.get("mcp_error")
        tool_name = str(result.get("tool_name") or "")
        parts = ["[MCP indisponível ou degradado]", f"tool={tool_name}", f"nota={note}"]
        if err:
            parts.append(f"erro={str(err)[:400]}")
        text = "\n".join(parts)
        return _clip_by_lines(text, max_chars)

    if isinstance(result.get("query_id"), str) and result["query_id"].strip():
        text = _summarize_catalog_query_payload(
            result,
            preview_rows=preview_rows,
            max_chars=max_chars,
            catalog_full_rows=catalog_full_rows,
        )
        if len(text) > max_chars:
            return _clip_by_lines(text, max_chars)
        return text

    if "sum_value" in result and "metric" in result and isinstance(result.get("metric"), str):
        text = _summarize_stub_like(result)
        return _clip_by_lines(text, max_chars)

    return _fallback_generic_json(result, max_chars=max_chars)


def _summarize_stub_like(result: dict[str, Any]) -> str:
    metric = result.get("metric")
    rows = result.get("rows")
    sv = result.get("sum_value")
    note = result.get("note")
    lines = [
        "### Analytics (stub ou agregado)",
        f"- métrica: {metric}",
        f"- linhas (contagem lógica): {rows}",
        f"- sum_value: {sv}",
    ]
    if note:
        lines.append(f"- nota: {note}")
    return "\n".join(lines)


def _summarize_catalog_query_payload(
    result: dict[str, Any],
    *,
    preview_rows: int,
    max_chars: int,
    catalog_full_rows: bool = False,
) -> str:
    if isinstance(result.get("drl_summary"), dict):
        return _summarize_drl_payload(result, max_chars=max_chars)
    qid = str(result.get("query_id") or "").strip()
    shape = str(result.get("output_shape") or "")
    row_count = _safe_int(result.get("row_count"), 0)
    limit = _safe_int(result.get("limit"), 0)
    offset = _safe_int(result.get("offset"), 0)
    summarize = bool(result.get("summarize"))

    rows_sample = result.get("rows_sample")
    rows_full = result.get("rows")
    if isinstance(rows_sample, list):
        preview_source: list[dict[str, Any]] = [r for r in rows_sample if isinstance(r, dict)]
        sample_label = "rows_sample (modo compacto)"
    elif isinstance(rows_full, list):
        preview_source = [r for r in rows_full if isinstance(r, dict)]
        sample_label = (
            "rows (página completa no payload)"
            if catalog_full_rows
            else "rows (pré-visualização)"
        )
    else:
        preview_source = []
        sample_label = "rows"

    if catalog_full_rows and isinstance(rows_full, list):
        n_cap = len(preview_source)
    else:
        n_cap = max(0, min(preview_rows, len(preview_source)))
    preview_slice = preview_source[:n_cap]

    header_lines: list[str] = [
        "### Resultado de consulta catalogada",
        f"- query_id: {qid}",
        f"- output_shape: {shape}",
        f"- row_count (página): {row_count}",
        f"- limit: {limit}, offset: {offset}, summarize: {summarize}",
    ]
    if limit > 0 and row_count >= limit:
        header_lines.append(
            "- aviso: row_count >= limit — pode haver mais páginas (aumentar limit ou usar offset)."
        )

    note = result.get("note") or result.get("payload_note")
    if isinstance(note, str) and note.strip():
        header_lines.append(f"- nota MCP: {note.strip()[:500]}")

    header = "\n".join(header_lines)
    max_c = max(256, int(max_chars))

    shown = 0
    row_lines: list[str] = []
    lines = list(header_lines)

    if preview_slice:
        cols = list(preview_slice[0].keys())
        col_line = f"- colunas ({sample_label}): {', '.join(cols)}"
        preview_heading = (
            "### Dados tabulares (página)" if catalog_full_rows else "### Pré-visualização"
        )
        # Orçamento só para linhas tabulares (cabeçalhos + rodapés contam para max_c).
        footer_reserve = 240
        overhead = len(header) + 1 + len(col_line) + 1 + len(preview_heading) + 1 + footer_reserve
        budget_rows = max(0, max_c - overhead)

        for row in preview_slice:
            line = _format_row(row)
            cand = _joined_row_block_len(row_lines + [line])
            if cand > budget_rows:
                if not row_lines and len(line) > budget_rows:
                    row_lines.append(line[: max(0, budget_rows - 3)] + "…")
                break
            row_lines.append(line)

        shown = len(row_lines)
        lines.append(col_line)
        lines.append(preview_heading)
        lines.extend(row_lines)
        lines.append(
            f"- linhas incluídas no prompt: {shown} de {len(preview_source)} "
            f"(teto caracteres={max_c}"
            + (", ORION_TOOL_LLM_CATALOG_FULL_ROWS=true" if catalog_full_rows else "")
            + ")"
        )
        omitted_by_chars = n_cap - shown
        omitted_by_preview_cap = len(preview_source) - n_cap
        if omitted_by_chars > 0:
            if catalog_full_rows:
                lines.append(
                    f"… ({omitted_by_chars} linhas não incluídas por teto de caracteres — "
                    "aumenta ORION_LLM_CONTEXT_MAX_CHARS (com full rows) ou ORION_TOOL_LLM_SUMMARY_MAX_CHARS)"
                )
            else:
                lines.append(
                    f"… ({omitted_by_chars} linhas não incluídas — aumenta "
                    "ORION_TOOL_LLM_SUMMARY_MAX_CHARS ou reduz ORION_TOOL_LLM_PREVIEW_ROWS)"
                )
        elif omitted_by_preview_cap > 0:
            lines.append(
                f"… ({omitted_by_preview_cap} linhas adicionais na amostra não mostradas "
                f"— aumenta ORION_TOOL_LLM_PREVIEW_ROWS ou activa ORION_TOOL_LLM_CATALOG_FULL_ROWS)"
            )
    else:
        lines.append(
            "### Dados tabulares (página)" if catalog_full_rows else "### Pré-visualização"
        )
        lines.append("(sem linhas tabulares no payload)")

    text = "\n".join(lines)
    # Garantir teto duro mesmo se rodapés excederem a reserva de caracteres.
    while len(text) > max_c and preview_slice and row_lines:
        row_lines.pop()
        shown = len(row_lines)
        lines = list(header_lines)
        cols = list(preview_slice[0].keys())
        col_line = f"- colunas ({sample_label}): {', '.join(cols)}"
        lines.append(col_line)
        lines.append(
            "### Dados tabulares (página)" if catalog_full_rows else "### Pré-visualização"
        )
        lines.extend(row_lines)
        lines.append(
            f"- linhas incluídas no prompt: {shown} de {len(preview_source)} "
            f"(teto caracteres={max_c}"
            + (", ORION_TOOL_LLM_CATALOG_FULL_ROWS=true" if catalog_full_rows else "")
            + ")"
        )
        omitted_by_chars = n_cap - shown
        omitted_by_preview_cap = len(preview_source) - n_cap
        if omitted_by_chars > 0:
            if catalog_full_rows:
                lines.append(
                    f"… ({omitted_by_chars} linhas não incluídas por teto de caracteres — "
                    "aumenta ORION_LLM_CONTEXT_MAX_CHARS (com full rows) ou ORION_TOOL_LLM_SUMMARY_MAX_CHARS)"
                )
            else:
                lines.append(
                    f"… ({omitted_by_chars} linhas não incluídas — aumenta "
                    "ORION_TOOL_LLM_SUMMARY_MAX_CHARS ou reduz ORION_TOOL_LLM_PREVIEW_ROWS)"
                )
        elif omitted_by_preview_cap > 0:
            lines.append(
                f"… ({omitted_by_preview_cap} linhas adicionais na amostra não mostradas "
                f"— aumenta ORION_TOOL_LLM_PREVIEW_ROWS ou activa ORION_TOOL_LLM_CATALOG_FULL_ROWS)"
            )
        text = "\n".join(lines)
    return text


def _fallback_generic_json(result: dict[str, Any], *, max_chars: int) -> str:
    text = json.dumps(result, ensure_ascii=False, sort_keys=True)
    if len(text) <= max_chars:
        return text
    lines = text.split("\n")
    if len(lines) > 1:
        return (
            "[resultado genérico demasiado grande para JSON completo]\n"
            + "\n".join(lines[:40])
            + f"\n… [truncado a ~40 linhas; teto {max_chars}]"
        )
    return text[: max_chars - 40] + "…[truncado]"

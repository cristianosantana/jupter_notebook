"""HTML para mensagens do assistente (chunks, content_blocks, TSV). Sem Streamlit."""

from __future__ import annotations

import re
from html import escape
from typing import Any

from smartchat.message_processing.cell_format import format_table_cell, infer_table_cell_kind, table_cell_tooltip
from smartchat.message_processing.chunks import (
    AssistantChunk,
    ChunkBullets,
    ChunkChoice,
    ChunkHeading,
    ChunkNumbered,
    ChunkParagraph,
    ChunkPipeTable,
    ChunkSpacer,
    parse_assistant_chunks,
    trim_spacer_edges,
)
from smartchat.message_processing.dedupe import ExtractedTsvTable
from smartchat.message_processing.merge_display import MergedAssistantDisplay

PROSE_CLASS = "sc-prose"


def render_inline_bold_html(text: str) -> str:
    parts = re.split(r"(\*\*[^*]+\*\*)", text)
    out: list[str] = []
    for part in parts:
        m = re.match(r"^\*\*([^*]+)\*\*$", part)
        if m:
            out.append(f"<strong>{escape(m.group(1))}</strong>")
        else:
            out.append(escape(part))
    return "".join(out)


def _cell_attrs(raw: Any) -> str:
    kind = infer_table_cell_kind(raw)
    tip = table_cell_tooltip(raw)
    t_attr = f' title="{escape(tip)}"' if tip else ""
    return f' data-cell-kind="{escape(kind)}"{t_attr}'


def _td_cell(raw: Any) -> str:
    disp = format_table_cell(raw)
    return f"<td{_cell_attrs(raw)}>{render_inline_bold_html(disp)}</td>"


PIPE_CELL_MONTH_VALUE = re.compile(
    r"^([A-Za-zÀ-ú]{3,})\s+(?:R\$\s*)?([\d\s.,]+(?:\s*[%‰])?)$"
)


def try_month_value_semantic_table(matrix: list[list[str]]) -> tuple[list[str], list[str]] | None:
    if len(matrix) != 1:
        return None
    cells = matrix[0]
    headers: list[str] = []
    values: list[str] = []
    for c in cells:
        m = PIPE_CELL_MONTH_VALUE.match(c.strip())
        if not m:
            return None
        headers.append(m.group(1))
        values.append(m.group(2).strip())
    return (headers, values) if len(headers) >= 2 else None


def pipe_table_rows_to_html(rows: list[str]) -> str:
    from smartchat.message_processing.chunks import split_pipe_cells

    matrix = [split_pipe_cells(r) for r in rows]
    if not matrix or all(len(r) == 0 for r in matrix):
        return ""
    max_cols = max(len(r) for r in matrix)
    semantic = try_month_value_semantic_table(matrix)
    wrap_open = '<div class="sc-table-wrap"><div class="sc-table-inner"><table class="sc-table">'
    wrap_close = "</table></div></div>"
    if semantic:
        headers, values = semantic
        thead = "<thead><tr>" + "".join(
            f'<th>{render_inline_bold_html(h)}</th>' for h in headers
        ) + "</tr></thead>"
        tbody = "<tbody><tr>" + "".join(_td_cell(v) for v in values) + "</tr></tbody>"
        return wrap_open + thead + tbody + wrap_close
    body_rows = []
    for row in matrix:
        tds = []
        for ci in range(max_cols):
            cell = row[ci] if ci < len(row) else None
            empty = cell is None or cell == ""
            if empty:
                tds.append('<td data-cell-kind="empty">—</td>')
            else:
                tds.append(_td_cell(cell))
        body_rows.append("<tr>" + "".join(tds) + "</tr>")
    return wrap_open + "<tbody>" + "".join(body_rows) + "</tbody>" + wrap_close


def assistant_chunks_to_html(chunks: list[AssistantChunk]) -> str:
    parts: list[str] = []
    for chunk in chunks:
        if isinstance(chunk, ChunkSpacer):
            parts.append('<div class="sc-spacer" aria-hidden="true"></div>')
        elif isinstance(chunk, ChunkHeading):
            tag = "h3" if chunk.level == 1 else "h4" if chunk.level == 2 else "h5"
            cls = "sc-h1" if chunk.level == 1 else "sc-h2" if chunk.level == 2 else "sc-h3"
            parts.append(
                f'<div class="{PROSE_CLASS}"><{tag} class="{cls}">'
                f"{render_inline_bold_html(chunk.text)}</{tag}></div>"
            )
        elif isinstance(chunk, ChunkNumbered):
            segments = [s.strip() for s in re.split(r"\s+[—–]\s+", chunk.raw) if s.strip()]
            head = segments[0] if segments else ""
            rest = segments[1:]
            inner = ""
            if head:
                inner += f'<p class="sc-num-head">{render_inline_bold_html(head)}</p>'
            if rest:
                inner += '<ul class="sc-num-rest">' + "".join(
                    f'<li>{render_inline_bold_html(seg)}</li>' for seg in rest
                ) + "</ul>"
            parts.append(f'<div class="{PROSE_CLASS} sc-numbered-card">{inner}</div>')
        elif isinstance(chunk, ChunkBullets) and chunk.items:
            lis = "".join(f"<li>{render_inline_bold_html(it)}</li>" for it in chunk.items)
            parts.append(
                f'<div class="{PROSE_CLASS}"><ul class="sc-bullets">{lis}</ul></div>'
            )
        elif isinstance(chunk, ChunkChoice):
            parts.append(
                f'<div class="{PROSE_CLASS}"><div class="sc-choice">'
                f'<span class="sc-choice-badge">{escape(chunk.letter)}</span>'
                f'<p class="sc-choice-text">{render_inline_bold_html(chunk.rest)}</p></div></div>'
            )
        elif isinstance(chunk, ChunkPipeTable) and chunk.rows:
            cap = ""
            if chunk.caption:
                cap = (
                    f'<p class="sc-pipe-caption">{render_inline_bold_html(chunk.caption)}</p>'
                )
            parts.append(
                f'<div class="sc-pipe-block">{cap}<div class="sc-pipe-center">'
                f"{pipe_table_rows_to_html(chunk.rows)}</div></div>"
            )
        elif isinstance(chunk, ChunkParagraph) and chunk.lines:
            spans = "".join(
                f'<span class="sc-para-line">{render_inline_bold_html(ln)}</span>'
                for ln in chunk.lines
            )
            parts.append(f'<div class="{PROSE_CLASS}"><p class="sc-paragraph">{spans}</p></div>')
    return f'<div class="sc-assistant-body">{"".join(parts)}</div>'


def prose_only_html(content: str) -> str:
    lines = content.split("\n")
    chunks = trim_spacer_edges(parse_assistant_chunks(lines))
    return assistant_chunks_to_html(chunks)


def content_blocks_to_html(blocks: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for b in blocks:
        t = b.get("type")
        if t == "paragraph" and isinstance(b.get("text"), str):
            parts.append(
                f'<div class="{PROSE_CLASS}"><p class="sc-cb-para">'
                f"{escape(b['text']).replace(chr(10), '<br/>')}</p></div>"
            )
        elif t == "heading" and isinstance(b.get("text"), str):
            lv = int(b.get("level") or 2)
            tag = "h3" if lv == 1 else "h4" if lv == 2 else "h5"
            cls = "sc-h1" if lv == 1 else "sc-h2" if lv == 2 else "sc-h3"
            parts.append(
                f'<div class="{PROSE_CLASS}"><{tag} class="{cls}">'
                f"{escape(b['text'])}</{tag}></div>"
            )
        elif t == "table":
            cols = b.get("columns")
            rows = b.get("rows")
            if not isinstance(cols, list) or not isinstance(rows, list):
                continue
            thead = "<thead><tr>" + "".join(f"<th>{escape(str(c))}</th>" for c in cols) + "</tr></thead>"
            body = ""
            for row in rows:
                if not isinstance(row, list):
                    continue
                tds = []
                for ci in range(len(cols)):
                    raw = row[ci] if ci < len(row) else None
                    tds.append(_td_cell(raw))
                body += "<tr>" + "".join(tds) + "</tr>"
            parts.append(
                '<div class="sc-cb-table-outer"><div class="sc-table-wrap">'
                '<div class="sc-table-inner"><table class="sc-table sc-table-bordered">'
                f"{thead}<tbody>{body}</tbody></table></div></div></div>"
            )
        elif t == "metric_grid" and isinstance(b.get("items"), list):
            items = b["items"]
            lis = []
            for it in items:
                if not isinstance(it, dict):
                    continue
                lab = str(it.get("label", ""))
                val = it.get("value", "")
                lis.append(
                    '<li class="sc-metric-card">'
                    f'<div class="sc-metric-label">{escape(lab)}</div>'
                    f'<div class="sc-metric-value"{_cell_attrs(val)}>'
                    f"{render_inline_bold_html(format_table_cell(val))}</div></li>"
                )
            parts.append(f'<ul class="sc-metric-grid">{"".join(lis)}</ul>')
    return f'<div class="sc-content-blocks">{"".join(parts)}</div>'


def tsv_table_to_html(table: ExtractedTsvTable) -> str:
    title = ""
    if table.title_line:
        title = f'<p class="sc-tsv-title">{escape(table.title_line)}</p>'
    thead = "<thead><tr>" + "".join(f"<th>{escape(c)}</th>" for c in table.columns) + "</tr></thead>"
    body = ""
    for row in table.rows:
        tds = []
        for ci in range(len(table.columns)):
            raw = row[ci] if ci < len(row) else None
            tds.append(_td_cell(raw))
        body += "<tr>" + "".join(tds) + "</tr>"
    tbl = (
        '<div class="sc-table-wrap"><div class="sc-table-inner">'
        '<table class="sc-table sc-table-bordered">'
        f"{thead}<tbody>{body}</tbody></table></div></div>"
    )
    return f'<div class="sc-tsv-block">{title}{tbl}</div>'


def merged_display_to_html(merged: MergedAssistantDisplay) -> str:
    has_structured = (merged.merged_blocks and merged.merged_blocks.get("blocks")) or (
        merged.tsv_inline is not None
    )
    if not has_structured:
        return prose_only_html(merged.display_content)
    pieces: list[str] = []
    if merged.display_content.strip():
        pieces.append(prose_only_html(merged.display_content))
    raw_blocks = merged.merged_blocks.get("blocks") if merged.merged_blocks else None
    if isinstance(raw_blocks, list) and raw_blocks:
        typed = [x for x in raw_blocks if isinstance(x, dict)]
        pieces.append(content_blocks_to_html(typed))
    if merged.tsv_inline is not None:
        pieces.append(tsv_table_to_html(merged.tsv_inline))
    return f'<div class="sc-assistant-structured">{"".join(pieces)}</div>'

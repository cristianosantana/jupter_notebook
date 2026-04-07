"""Dedupe lista vs tabela e extração TSV (espelho de dedupeAssistantProse.ts)."""

from __future__ import annotations

import re
from dataclasses import dataclass


def _is_concessionaria_list_line(line: str) -> bool:
    t = line.strip()
    if len(t) < 28:
        return False
    if not re.search(r"\bOS\s*\d+", t, re.I):
        return False
    if not re.search(r"Recebido", t, re.I):
        return False
    if not re.search(r"Pendente", t, re.I):
        return False
    if not re.search(r"Previsto|Faturamento\s+Previsto", t, re.I):
        return False
    return True


def _is_list_intro_line(line: str) -> bool:
    t = line.strip()
    if len(t) > 200:
        return False
    return bool(re.search(r"detalhamento\s+por\s+concession", t, re.I)) or bool(
        re.search(r"lista\s+por\s+unidade", t, re.I)
    )


def strip_duplicate_concessionaria_list(prose: str, reference_row_count: int | None) -> str:
    if reference_row_count is None or reference_row_count < 3:
        return prose
    lines = prose.split("\n")
    runs: list[tuple[int, int]] = []
    i = 0
    while i < len(lines):
        if not _is_concessionaria_list_line(lines[i]):
            i += 1
            continue
        start = i
        while i < len(lines) and _is_concessionaria_list_line(lines[i]):
            i += 1
        runs.append((start, i))
    exact = next((r for r in runs if r[1] - r[0] == reference_row_count), None)
    near = next(
        (
            r
            for r in runs
            if abs(r[1] - r[0] - reference_row_count) <= 1 and r[1] - r[0] >= 3
        ),
        None,
    )
    to_remove = exact or near
    if not to_remove:
        return prose
    rm_start = to_remove[0]
    if rm_start > 0 and _is_list_intro_line(lines[rm_start - 1]):
        rm_start -= 1
    out = lines[:rm_start] + lines[to_remove[1] :]
    text = "\n".join(out)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.rstrip()


def tab_split(line: str) -> list[str]:
    return [c.strip() for c in line.split("\t")]


def _is_tsv_row(line: str, min_cols: int) -> bool:
    if "\t" not in line:
        return False
    parts = [p for p in tab_split(line) if p]
    return len(parts) >= min_cols


def find_tsv_block(lines: list[str]) -> tuple[int, int, list[str], list[list[str]]] | None:
    best: tuple[int, int, list[str], list[list[str]]] | None = None
    for start in range(len(lines)):
        if "\t" not in lines[start]:
            continue
        first_parts = tab_split(lines[start])
        if len(first_parts) < 3:
            continue
        end = start + 1
        while end < len(lines) and _is_tsv_row(lines[end], 3):
            end += 1
        slice_lines = lines[start:end]
        if len(slice_lines) < 2:
            continue
        columns = tab_split(slice_lines[0])
        if len(columns) < 3:
            continue
        data_rows = [tab_split(ln) for ln in slice_lines[1:]]
        if len(data_rows) < 2:
            continue
        header_ok = bool(
            re.search(
                r"concession|qtd|recebido|pendente|previsto|faturamento|mês|mes",
                slice_lines[0],
                re.I,
            )
        )
        if not header_ok and len(columns) < 4:
            continue
        if best is None or len(data_rows) > len(best[3]) or (
            len(data_rows) == len(best[3]) and len(columns) > len(best[2])
        ):
            best = (start, end, columns, data_rows)
    return best


def peek_tsv_data_row_count(prose: str) -> int | None:
    block = find_tsv_block(prose.split("\n"))
    return len(block[3]) if block else None


@dataclass
class ExtractedTsvTable:
    title_line: str | None
    columns: list[str]
    rows: list[list[str]]
    data_row_count: int


@dataclass
class ExtractTsvResult:
    prose_without_table: str
    table: ExtractedTsvTable | None


def extract_tsv_table_from_prose(prose: str) -> ExtractTsvResult:
    lines = prose.split("\n")
    block = find_tsv_block(lines)
    if not block:
        return ExtractTsvResult(prose_without_table=prose, table=None)
    start, end, columns, data_rows = block
    title_line: str | None = None
    if start > 0:
        prev = lines[start - 1].strip()
        if (
            prev
            and len(prev) < 220
            and "\t" not in prev
            and not _is_concessionaria_list_line(lines[start - 1])
        ):
            title_line = prev
    rm_start = start - 1 if title_line else start
    before = "\n".join(lines[:rm_start]).rstrip()
    after = "\n".join(lines[end:]).lstrip()
    prose_without = "\n\n".join(x for x in (before, after) if x).strip()
    return ExtractTsvResult(
        prose_without_table=prose_without,
        table=ExtractedTsvTable(
            title_line=title_line,
            columns=columns,
            rows=data_rows,
            data_row_count=len(data_rows),
        ),
    )

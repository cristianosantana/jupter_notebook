"""Parse de prosa do assistente em chunks (espelho de parseAssistantChunks no App.tsx)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal


def split_pipe_cells(line: str) -> list[str]:
    return [c.strip() for c in line.split("|") if c.strip()]


def count_pipes(s: str) -> int:
    return len(re.findall(r"\|", s))


def is_pipe_dense_line(s: str) -> bool:
    return count_pipes(s) >= 2 and len(split_pipe_cells(s)) >= 2


def extract_pipe_table_from_line(line: str) -> tuple[str | None, str]:
    trimmed = line.strip()
    if not is_pipe_dense_line(trimmed):
        return None, trimmed
    first_pipe = trimmed.index("|")
    preamble = trimmed[:first_pipe].strip()
    rest = trimmed[first_pipe:].strip()
    if not is_pipe_dense_line(rest):
        return None, trimmed
    caption = preamble if preamble else None
    return caption, rest


@dataclass
class ChunkSpacer:
    kind: Literal["spacer"] = "spacer"


@dataclass
class ChunkHeading:
    kind: Literal["heading"] = "heading"
    level: int = 2
    text: str = ""


@dataclass
class ChunkNumbered:
    kind: Literal["numbered"] = "numbered"
    raw: str = ""


@dataclass
class ChunkBullets:
    kind: Literal["bullets"] = "bullets"
    items: list[str] | None = None


@dataclass
class ChunkParagraph:
    kind: Literal["paragraph"] = "paragraph"
    lines: list[str] | None = None


@dataclass
class ChunkChoice:
    kind: Literal["choice"] = "choice"
    letter: str = ""
    rest: str = ""


@dataclass
class ChunkPipeTable:
    kind: Literal["pipe_table"] = "pipe_table"
    rows: list[str] | None = None
    caption: str | None = None


AssistantChunk = (
    ChunkSpacer
    | ChunkHeading
    | ChunkNumbered
    | ChunkBullets
    | ChunkParagraph
    | ChunkChoice
    | ChunkPipeTable
)


def parse_assistant_chunks(lines: list[str]) -> list[AssistantChunk]:
    chunks: list[AssistantChunk] = []
    i = 0
    while i < len(lines):
        trimmed = lines[i].strip()
        if not trimmed:
            chunks.append(ChunkSpacer())
            i += 1
            continue
        md_heading = re.match(r"^(#{1,3})\s+(.+)$", trimmed)
        if md_heading:
            n = len(md_heading.group(1))
            chunks.append(ChunkHeading(level=n, text=md_heading.group(2)))
            i += 1
            continue
        if re.match(r"^(?:\d+\)|\d+\.\s)", trimmed):
            chunks.append(ChunkNumbered(raw=trimmed))
            i += 1
            continue
        choice = re.match(r"^\(([A-Za-z])\)\s*(.+)$", trimmed)
        if choice and choice.group(2).strip():
            chunks.append(
                ChunkChoice(letter=choice.group(1).upper(), rest=choice.group(2).strip())
            )
            i += 1
            continue
        if re.match(r"^[-•*]\s", trimmed):
            items: list[str] = []
            while i < len(lines):
                t = lines[i].strip()
                if re.match(r"^[-•*]\s", t):
                    items.append(re.sub(r"^[-•*]\s+", "", t))
                    i += 1
                else:
                    break
            chunks.append(ChunkBullets(items=items))
            continue
        if is_pipe_dense_line(trimmed):
            first_cap, pipe_line = extract_pipe_table_from_line(trimmed)
            row_list = [pipe_line]
            caption = first_cap
            i += 1
            while i < len(lines):
                t = lines[i].strip()
                if not t:
                    break
                if not is_pipe_dense_line(t):
                    break
                n_cap, n_line = extract_pipe_table_from_line(t)
                if n_cap:
                    break
                row_list.append(n_line)
                i += 1
            chunks.append(ChunkPipeTable(rows=row_list, caption=caption))
            continue
        para_lines: list[str] = []
        while i < len(lines):
            t = lines[i].strip()
            if not t:
                break
            if (
                re.match(r"^(#{1,3})\s+", t)
                or re.match(r"^(?:\d+\)|\d+\.\s)", t)
                or re.match(r"^\([A-Za-z]\)\s", t)
                or re.match(r"^[-•*]\s", t)
                or is_pipe_dense_line(t)
            ):
                break
            para_lines.append(t)
            i += 1
        chunks.append(ChunkParagraph(lines=para_lines))
    return chunks


def trim_spacer_edges(chunks: list[AssistantChunk]) -> list[AssistantChunk]:
    out = list(chunks)
    while out and isinstance(out[0], ChunkSpacer):
        out = out[1:]
    while out and isinstance(out[-1], ChunkSpacer):
        out = out[:-1]
    collapsed: list[AssistantChunk] = []
    for c in out:
        if isinstance(c, ChunkSpacer) and collapsed and isinstance(collapsed[-1], ChunkSpacer):
            continue
        collapsed.append(c)
    return collapsed

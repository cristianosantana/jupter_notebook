"""Divide validated_answer em secções nomeadas."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from orion_mcp_v3.public_chat.domain.knowledge import KnowledgeHit

_KNOWN_HEADERS = (
    "Formas de pagamento",
    "Tipos de venda",
    "Produção por serviço",
    "Producao por servico",
    "Produção por produto",
    "Producao por produto",
    "Parcelamento",
    "Parcelamento de cartão",
    "Taxas",
    "Comissão",
    "Comissao",
)

_HEADER_PATTERN = re.compile(
    r"(?m)^(?:"
    + "|".join(re.escape(item) for item in _KNOWN_HEADERS)
    + r"|Top\s+\d+[^\n]*|Comiss[aã]o[^\n]*)\s*(?:—|:|-)\s*",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class DocumentSection:
    id: str
    title: str
    body: str
    source_hit_id: int
    context_key: str


@dataclass(frozen=True, slots=True)
class ParsedDocument:
    context_key: str
    source_hit_id: int
    sections: tuple[DocumentSection, ...]


def parse_document(hit: KnowledgeHit) -> ParsedDocument:
    text = (hit.validated_answer or "").strip()
    if not text:
        return ParsedDocument(
            context_key=hit.context_key,
            source_hit_id=hit.origin_id,
            sections=(),
        )

    sections = _split_sections(text, hit=hit)
    if not sections:
        sections = (
            DocumentSection(
                id="s1",
                title="documento",
                body=text,
                source_hit_id=hit.origin_id,
                context_key=hit.context_key,
            ),
        )
    return ParsedDocument(
        context_key=hit.context_key,
        source_hit_id=hit.origin_id,
        sections=sections,
    )


def parse_documents(hits: tuple[KnowledgeHit, ...]) -> tuple[ParsedDocument, ...]:
    return tuple(parse_document(hit) for hit in hits)


def _split_sections(text: str, *, hit: KnowledgeHit) -> tuple[DocumentSection, ...]:
    matches = list(_HEADER_PATTERN.finditer(text))
    if not matches:
        matches = list(_colon_header_pattern().finditer(text))
    if not matches:
        return ()

    sections: list[DocumentSection] = []
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        chunk = text[start:end].strip()
        title = _normalize_title(match.group(0))
        body = chunk[len(match.group(0)) :].strip() or chunk
        sections.append(
            DocumentSection(
                id=f"s{index + 1}",
                title=title,
                body=body,
                source_hit_id=hit.origin_id,
                context_key=hit.context_key,
            )
        )
    return tuple(sections)


def _colon_header_pattern() -> re.Pattern[str]:
    return re.compile(r"(?m)^([A-ZÀ-Ú][^\n:]{2,80}):\s*")


def _normalize_title(raw: str) -> str:
    title = raw.strip().rstrip(":-—").strip()
    return title or "secção"

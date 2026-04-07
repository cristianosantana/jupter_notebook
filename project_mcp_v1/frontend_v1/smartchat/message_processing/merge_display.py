"""Junta texto, content_blocks da API, TSV e dedupe (espelho de StructuredAssistantMessage)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from smartchat.message_processing.blocks import extract_reply_content_blocks, parse_content_blocks
from smartchat.message_processing.dedupe import (
    ExtractedTsvTable,
    extract_tsv_table_from_prose,
    peek_tsv_data_row_count,
    strip_duplicate_concessionaria_list,
)


@dataclass
class MergedAssistantDisplay:
    display_content: str
    merged_blocks: dict[str, Any] | None
    tsv_inline: ExtractedTsvTable | None


def _json_table_max_rows(blocks: dict[str, Any] | None) -> int:
    if not blocks:
        return 0
    raw = blocks.get("blocks")
    if not isinstance(raw, list):
        return 0
    m = 0
    for b in raw:
        if not isinstance(b, dict) or b.get("type") != "table":
            continue
        rows = b.get("rows")
        if isinstance(rows, list):
            m = max(m, len(rows))
    return m


def merge_assistant_display(content: str, content_blocks_raw: Any) -> MergedAssistantDisplay:
    extracted_text, extracted_payload = extract_reply_content_blocks(content)
    from_api = parse_content_blocks(content_blocks_raw)
    if from_api and from_api.get("blocks"):
        blocks = from_api
    else:
        blocks = extracted_payload

    if extracted_payload is not None:
        text = extracted_text
    else:
        text = content

    json_max = _json_table_max_rows(blocks)
    tsv_peek = peek_tsv_data_row_count(text)
    ref_rows = max(json_max, tsv_peek or 0)
    if ref_rows >= 3:
        text = strip_duplicate_concessionaria_list(text, ref_rows)

    tsv_result = extract_tsv_table_from_prose(text)
    prose_without = tsv_result.prose_without_table
    tsv_raw = tsv_result.table

    has_json_table = False
    if blocks and isinstance(blocks.get("blocks"), list):
        for b in blocks["blocks"]:
            if isinstance(b, dict) and b.get("type") == "table":
                rows = b.get("rows")
                if isinstance(rows, list) and len(rows) >= 2:
                    has_json_table = True
                    break

    tsv_inline = None if has_json_table else tsv_raw

    return MergedAssistantDisplay(
        display_content=prose_without,
        merged_blocks=blocks,
        tsv_inline=tsv_inline,
    )

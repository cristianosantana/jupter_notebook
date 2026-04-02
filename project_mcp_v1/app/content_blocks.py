"""
Extracção e validação de ``content_blocks`` JSON opcional no texto do assistente.

O modelo pode terminar a mensagem com um fenced block `` ```json ... ``` `` contendo
``{"version": 1, "blocks": [...]}`` para o SmartChat renderizar tabelas / métricas.
"""

from __future__ import annotations

import json
import re
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Field, ValidationError

__all__ = [
    "ContentBlocksPayload",
    "split_reply_and_blocks",
]


class BlockParagraph(BaseModel):
    type: Literal["paragraph"] = "paragraph"
    text: str


class BlockHeading(BaseModel):
    type: Literal["heading"] = "heading"
    level: Literal[1, 2, 3] = 2
    text: str


class BlockTable(BaseModel):
    type: Literal["table"] = "table"
    columns: list[str]
    rows: list[list[Any]]


class BlockMetricItem(BaseModel):
    label: str
    value: str


class BlockMetricGrid(BaseModel):
    type: Literal["metric_grid"] = "metric_grid"
    items: list[BlockMetricItem]


ContentBlock = Annotated[
    Union[BlockParagraph, BlockHeading, BlockTable, BlockMetricGrid],
    Field(discriminator="type"),
]


class ContentBlocksPayload(BaseModel):
    version: Literal[1] = 1
    blocks: list[ContentBlock]


_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)


def split_reply_and_blocks(assistant_content: str) -> tuple[str, dict[str, Any] | None]:
    """
    Remove o último fenced JSON válido (``ContentBlocksPayload``) do texto e devolve
    ``(texto_para_o_utilizador, payload_serializado_ou_None)``.
    """
    if not assistant_content or not assistant_content.strip():
        return assistant_content, None
    text = assistant_content
    matches = list(_FENCE_RE.finditer(text))
    for m in reversed(matches):
        raw = m.group(1).strip()
        if not raw.startswith("{"):
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict) or "blocks" not in data:
            continue
        try:
            payload = ContentBlocksPayload.model_validate(data)
        except ValidationError:
            continue
        before = text[: m.start()].rstrip()
        after = text[m.end() :].lstrip()
        display = f"{before}\n\n{after}".strip() if after else before
        return display, payload.model_dump(mode="json")
    stripped = text.strip()
    if stripped.startswith("{") and '"blocks"' in stripped:
        try:
            data = json.loads(stripped)
            payload = ContentBlocksPayload.model_validate(data)
            return "", payload.model_dump(mode="json")
        except (json.JSONDecodeError, ValidationError):
            pass
    return assistant_content, None

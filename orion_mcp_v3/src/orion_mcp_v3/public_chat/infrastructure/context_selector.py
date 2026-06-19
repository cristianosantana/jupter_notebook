"""Selector LLM de secções relevantes."""

from __future__ import annotations

import json
import time

from orion_mcp_v3.protocols.llm import ChatMessage, LLMProvider
from orion_mcp_v3.public_chat.domain.intent_contract import IntentContract
from orion_mcp_v3.public_chat.domain.intent_parser import parse_json_object
from orion_mcp_v3.public_chat.domain.section_parser import DocumentSection, ParsedDocument
from orion_mcp_v3.public_chat.domain.selected_context import SelectedContext
from orion_mcp_v3.public_chat.infrastructure.pipeline_trace import log_public_chat_event, preview_message
from orion_mcp_v3.public_chat.prompts import get_public_chat_prompt_registry

_SYSTEM_PROMPT = get_public_chat_prompt_registry().get_text("public_chat_context_selector.system")
_PREVIEW_LEN = 200


class PublicContextSelector:
    def __init__(self, provider: LLMProvider, *, max_tokens: int = 256) -> None:
        self._provider = provider
        self._max_tokens = max_tokens

    async def select(
        self,
        message: str,
        *,
        contract: IntentContract,
        documents: tuple[ParsedDocument, ...],
    ) -> SelectedContext:
        t0 = time.monotonic()
        catalog = _build_section_catalog(documents)
        source_chars = sum(len(section.body) for section in catalog.values())

        log_public_chat_event(
            etapa="selector.select",
            fase="pre",
            dados={
                **preview_message(message),
                "section_count": len(catalog),
                "document_count": len(documents),
                "source_context_chars": source_chars,
            },
        )

        if not catalog:
            selected = SelectedContext(
                sections=(),
                selection_reason="no_sections_available",
                degraded=True,
                source_context_chars=source_chars,
            )
            _log_post(t0, selected)
            return selected

        prompt = json.dumps(
            {
                "user_message": message,
                "intent_contract": contract.as_mapping(),
                "available_sections": [
                    {
                        "id": section_id,
                        "title": section.title,
                        "preview": _preview(section.body),
                        "context_key": section.context_key,
                    }
                    for section_id, section in catalog.items()
                ],
                "required_json_shape": {
                    "selected_section_ids": ["string"],
                    "reason": "string",
                },
            },
            ensure_ascii=False,
            default=str,
        )

        try:
            response = await self._provider.chat(
                [
                    ChatMessage(role="system", content=_SYSTEM_PROMPT),
                    ChatMessage(role="user", content=prompt),
                ],
                max_tokens=self._max_tokens,
                temperature=0,
            )
            payload = parse_json_object(response.text)
        except Exception as exc:
            selected = _degraded_fallback(
                catalog,
                reason=f"selector_error:{type(exc).__name__}",
                source_chars=source_chars,
            )
            _log_post(t0, selected, error=str(exc))
            return selected

        selected = _parse_selection(payload, catalog=catalog, source_chars=source_chars)
        _log_post(t0, selected)
        return selected


def _build_section_catalog(documents: tuple[ParsedDocument, ...]) -> dict[str, DocumentSection]:
    catalog: dict[str, DocumentSection] = {}
    for document in documents:
        for section in document.sections:
            key = f"{document.source_hit_id}:{section.id}"
            catalog[key] = DocumentSection(
                id=key,
                title=section.title,
                body=section.body,
                source_hit_id=section.source_hit_id,
                context_key=section.context_key,
            )
    return catalog


def _parse_selection(
    payload: dict[str, object] | None,
    *,
    catalog: dict[str, DocumentSection],
    source_chars: int,
) -> SelectedContext:
    if not isinstance(payload, dict):
        return _degraded_fallback(catalog, reason="invalid_json", source_chars=source_chars)

    raw_ids = payload.get("selected_section_ids")
    reason = str(payload.get("reason") or "").strip() or None
    if not isinstance(raw_ids, list):
        return _degraded_fallback(catalog, reason="missing_section_ids", source_chars=source_chars)

    sections: list[DocumentSection] = []
    for item in raw_ids:
        section_id = str(item).strip()
        if section_id in catalog:
            sections.append(catalog[section_id])

    if not sections:
        return _degraded_fallback(catalog, reason=reason or "empty_selection", source_chars=source_chars)

    selected_chars = sum(len(section.body) for section in sections)
    return SelectedContext(
        sections=tuple(sections),
        selection_reason=reason,
        degraded=False,
        source_context_chars=source_chars,
        selected_context_chars=selected_chars,
    )


def _degraded_fallback(
    catalog: dict[str, DocumentSection],
    *,
    reason: str,
    source_chars: int,
) -> SelectedContext:
    sections = tuple(catalog.values())
    selected_chars = sum(len(section.body) for section in sections)
    return SelectedContext(
        sections=sections,
        selection_reason=reason,
        degraded=True,
        source_context_chars=source_chars,
        selected_context_chars=selected_chars,
    )


def _preview(body: str) -> str:
    normalized = body.replace("\n", " ").strip()
    if len(normalized) <= _PREVIEW_LEN:
        return normalized
    return normalized[: _PREVIEW_LEN - 3] + "..."


def _log_post(t0: float, selected: SelectedContext, *, error: str | None = None) -> None:
    dados: dict[str, object] = {
        "latency_ms": round((time.monotonic() - t0) * 1000.0, 2),
        "selected_section_count": len(selected.sections),
        "degraded": selected.degraded,
        "selection_reason": selected.selection_reason,
        "source_context_chars": selected.source_context_chars,
        "selected_context_chars": selected.selected_context_chars,
        "selected_section_ids": [section.id for section in selected.sections],
        "selected_titles": [section.title for section in selected.sections],
    }
    if error:
        dados["error"] = error
    log_public_chat_event(etapa="selector.select", fase="post", dados=dados)

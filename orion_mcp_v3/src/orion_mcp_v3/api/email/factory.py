"""Factory que transforma texto narrativo em relatório de e-mail estruturado."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from orion_mcp_v3.api.email.classifier import EmailMessageType, classify_message
from orion_mcp_v3.api.email.merging import (
    merge_data_with_narrative,
    merge_narrative_reports,
    merge_with_fallback,
)
from orion_mcp_v3.api.email.models import EmailMetricItem, EmailReport, EmailSection
from orion_mcp_v3.api.email.parsing import (
    build_report_from_text,
    first_meaningful_line,
    has_explicit_synthesis,
    narrative_report_from_text,
)
from orion_mcp_v3.api.email.parsing_config import EmailParsingConfig, apply_parsing_policy
from orion_mcp_v3.prompts import get_prompt_registry
from orion_mcp_v3.protocols.llm import ChatMessage, LLMProvider, NullLLMProvider

_LOG = logging.getLogger("orion.api.email")

_SCHEMA_FECHAMENTO_GERENCIAL: dict[str, Any] = {
    "type": "fechamento_gerencial",
    "period": "string|null",
    "headline_value": "string|null",
    "headline_label": "string|null",
    "sections": [
        {
            "title": "string",
            "category": "payment|revenue|commission|production|fees|default",
            "total": "string|null",
            "highlight_label": "string|null",
            "highlight_value": "string|null",
            "highlight_pct": "string|null",
            "items": [{"label": "string", "value": "string|null", "pct": "string|null"}],
            "notes": ["string"],
            "risks": ["string"],
        }
    ],
    "alerts": ["string"],
    "actions": ["string"],
}

_SCHEMA_RANKING: dict[str, Any] = {
    "type": "ranking",
    "period": "string|null",
    "metric": "string|null",
    "dimension": "string|null",
    "headline_value": "string|null",
    "items": [{"rank": "number|null", "label": "string", "value": "string|null", "pct": "string|null"}],
    "notes": ["string"],
}

_SCHEMA_COMPARACAO: dict[str, Any] = {
    "type": "comparacao",
    "period": "string|null",
    "headline_label": "string|null",
    "headline_value": "string|null",
    "comparisons": [{"label": "string", "value": "string|null", "detail": "string|null"}],
    "alerts": ["string"],
    "actions": ["string"],
}

_SCHEMA_ANALISE_UNICA: dict[str, Any] = {
    "type": "analise_unica",
    "period": "string|null",
    "headline_label": "string|null",
    "headline_value": "string|null",
    "items": [{"label": "string", "value": "string|null", "detail": "string|null"}],
    "notes": ["string"],
    "actions": ["string"],
}

_SCHEMA_CONVERSACIONAL: dict[str, Any] = {
    "type": "conversacional",
    "message": "string",
}

_NARRATIVE_SCHEMA: dict[str, Any] = {
    "headline": "string|null",
    "executive_summary": "string|null, prefer the explicit 'Síntese curta de composição' when present",
    "alerts": ["strings explicitly mentioned as alerts or attention points"],
    "actions": ["strings explicitly mentioned as concrete recommendations"],
}


@dataclass(frozen=True, slots=True)
class ReportType:
    name: str
    schema: dict[str, Any]
    use_llm: bool = True

    def validate_schema(self) -> bool:
        if self.schema.get("type") != self.name:
            return False
        if self.name == "conversacional":
            return "message" in self.schema
        return "type" in self.schema


REGISTRY: dict[str, ReportType] = {
    "fechamento_gerencial": ReportType("fechamento_gerencial", _SCHEMA_FECHAMENTO_GERENCIAL),
    "ranking": ReportType("ranking", _SCHEMA_RANKING),
    "comparacao": ReportType("comparacao", _SCHEMA_COMPARACAO),
    "analise_unica": ReportType("analise_unica", _SCHEMA_ANALISE_UNICA),
    "conversacional": ReportType("conversacional", _SCHEMA_CONVERSACIONAL, use_llm=False),
}

for _report_type in REGISTRY.values():
    if not _report_type.validate_schema():
        raise ValueError(f"Schema inválido para report type: {_report_type.name}")


class EmailMessageFactory:
    """Monta um `EmailReport` validado a partir do texto da resposta."""

    def __init__(
        self,
        provider: LLMProvider | None = None,
        *,
        max_tokens: int = 1200,
        parsing_config: EmailParsingConfig | None = None,
    ) -> None:
        self._provider = provider or NullLLMProvider()
        self._max_tokens = max_tokens
        self._parsing_config = parsing_config

    async def build_report(
        self,
        *,
        subject: str,
        body: str,
        from_name: str = "Orion",
        structured_evidence: str | None = None,
        parsing_config: EmailParsingConfig | None = None,
    ) -> EmailReport:
        effective_config = parsing_config if parsing_config is not None else self._parsing_config
        source = structured_evidence or body
        message_type = classify_message(source)
        if structured_evidence:
            data_report = build_report_from_text(
                subject=subject,
                body=structured_evidence,
                from_name=from_name,
                report_type=message_type,
                config=effective_config,
            )
            narrative_report = await self._try_narrative_report(subject=subject, body=body, from_name=from_name)
            narrative_fallback = narrative_report_from_text(subject=subject, body=body, from_name=from_name)
            if narrative_report is None:
                narrative_report = narrative_fallback
            else:
                narrative_report = merge_narrative_reports(
                    narrative_report,
                    narrative_fallback,
                    prefer_fallback_summary=has_explicit_synthesis(body),
                )
            return self._with_parsing_policy(
                merge_data_with_narrative(data_report, narrative_report),
                effective_config,
            )
        if message_type == "conversacional":
            return _simple_report(subject=subject, body=body, from_name=from_name, report_type=message_type)
        fallback = build_report_from_text(
            subject=subject,
            body=source,
            from_name=from_name,
            report_type=message_type,
            config=effective_config,
        )
        report_type = REGISTRY.get(message_type)
        if report_type is not None and report_type.use_llm and not isinstance(self._provider, NullLLMProvider):
            report = await self._try_llm_report(subject=subject, body=source, from_name=from_name, message_type=message_type)
            if report is not None and (report.sections or report.alerts or report.actions or report.headline):
                return self._with_parsing_policy(
                    merge_with_fallback(report.with_defaults(subject=subject, from_name=from_name), fallback),
                    effective_config,
                )
        return fallback

    @staticmethod
    def _with_parsing_policy(
        report: EmailReport,
        config: EmailParsingConfig | None,
    ) -> EmailReport:
        if config is None:
            return report
        return apply_parsing_policy(report, config)

    async def _try_llm_report(
        self,
        *,
        subject: str,
        body: str,
        from_name: str,
        message_type: EmailMessageType,
    ) -> EmailReport | None:
        prompt = _build_prompt(subject=subject, body=body, from_name=from_name, message_type=message_type)
        try:
            response = await self._provider.chat(
                [
                    ChatMessage(role="system", content=_SYSTEM_PROMPT),
                    ChatMessage(role="user", content=prompt),
                ],
                max_tokens=self._max_tokens,
                temperature=0,
            )
        except Exception:
            _LOG.exception("email message factory provider failed")
            return None
        payload = _parse_json_object(response.text)
        if payload is None:
            return None
        return EmailReport.from_mapping(payload)

    async def _try_narrative_report(self, *, subject: str, body: str, from_name: str) -> EmailReport | None:
        if isinstance(self._provider, NullLLMProvider):
            return None
        prompt = _build_narrative_prompt(subject=subject, body=body, from_name=from_name)
        try:
            response = await self._provider.chat(
                [
                    ChatMessage(role="system", content=_SYSTEM_PROMPT),
                    ChatMessage(role="user", content=prompt),
                ],
                max_tokens=self._max_tokens,
                temperature=0,
            )
        except Exception:
            _LOG.exception("email narrative extractor provider failed")
            return None
        payload = _parse_json_object(response.text)
        if payload is None:
            return None
        return EmailReport.from_mapping(payload)


def _build_prompt(*, subject: str, body: str, from_name: str, message_type: EmailMessageType) -> str:
    report_type = REGISTRY[message_type]
    payload = {
        "subject": subject,
        "from_name": from_name,
        "message_type": message_type,
        "body": body,
        "required_json_shape": report_type.schema,
    }
    return json.dumps(payload, ensure_ascii=False)


def _build_narrative_prompt(*, subject: str, body: str, from_name: str) -> str:
    payload = {
        "subject": subject,
        "from_name": from_name,
        "body": body,
        "required_json_shape": _NARRATIVE_SCHEMA,
    }
    return json.dumps(payload, ensure_ascii=False)


def _simple_report(*, subject: str, body: str, from_name: str, report_type: str) -> EmailReport:
    text = first_meaningful_line(body) or body or ""
    return EmailReport(
        report_type=report_type,
        subject=subject,
        from_name=from_name,
        headline=subject or None,
        sections=(
            EmailSection(
                title="Mensagem",
                kind="conversational",
                items=(EmailMetricItem(label=text),) if text else (),
            ),
        ),
    )


def _parse_json_object(text: str) -> dict[str, Any] | None:
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:].strip()
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            obj = json.loads(raw[start : end + 1])
        except json.JSONDecodeError:
            return None
    return obj if isinstance(obj, dict) else None


try:
    _SYSTEM_PROMPT = get_prompt_registry().get_text("email_message_factory.system")
except KeyError:
    _SYSTEM_PROMPT = (
        "You structure a Portuguese executive email report. Return only valid JSON. "
        "Never generate HTML, never invent numbers, and preserve values exactly."
    )

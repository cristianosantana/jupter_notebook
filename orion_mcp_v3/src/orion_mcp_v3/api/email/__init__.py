"""API pública do módulo de e-mail."""

from orion_mcp_v3.api.email.classifier import EmailMessageType, classify_message
from orion_mcp_v3.api.email.factory import EmailMessageFactory, ReportType, REGISTRY
from orion_mcp_v3.api.email.parsing import build_report_from_text
from orion_mcp_v3.api.email.parsing_config import (
    EmailParsingConfig,
    apply_parsing_policy,
    get_parsing_config,
)
from orion_mcp_v3.api.email.parsing_rules import ParsingRulesConfig, SectionOpenRule, default_section_rules
from orion_mcp_v3.api.email.rule_engine import RuleEngine, build_report_from_rules
from orion_mcp_v3.api.email.html_renderer import render_response_email_html
from orion_mcp_v3.api.email.models import EmailMetricItem, EmailReport, EmailSection, EmailTable
from orion_mcp_v3.api.email.sender import EmailSender, EmailSendRequest, EmailSendResult

__all__ = [
    "EmailMessageFactory",
    "EmailMessageType",
    "EmailMetricItem",
    "EmailReport",
    "EmailSection",
    "EmailSender",
    "EmailSendRequest",
    "EmailSendResult",
    "EmailTable",
    "REGISTRY",
    "ReportType",
    "EmailParsingConfig",
    "apply_parsing_policy",
    "build_report_from_text",
    "get_parsing_config",
    "ParsingRulesConfig",
    "RuleEngine",
    "SectionOpenRule",
    "build_report_from_rules",
    "default_section_rules",
    "classify_message",
    "render_response_email_html",
]

"""API pública do módulo de e-mail."""

from orion_mcp_v3.api.email.classifier import EmailMessageType, classify_message
from orion_mcp_v3.api.email.factory import EmailMessageFactory, build_report_from_text
from orion_mcp_v3.api.email.html_renderer import render_response_email_html
from orion_mcp_v3.api.email.models import EmailMetricItem, EmailReport, EmailSection
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
    "build_report_from_text",
    "classify_message",
    "render_response_email_html",
]

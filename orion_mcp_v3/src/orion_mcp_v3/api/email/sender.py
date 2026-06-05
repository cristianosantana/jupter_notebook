"""Envio assíncrono de respostas do chat por e-mail."""

from __future__ import annotations

import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr
from typing import Literal

from orion_mcp_v3.api.email.factory import EmailMessageFactory
from orion_mcp_v3.api.email.html_renderer import render_response_email_html
from orion_mcp_v3.config.settings import OrionSettings
from orion_mcp_v3.protocols.llm import LLMProvider

_LOG = logging.getLogger("orion.api.email")

EmailSendStatus = Literal["not_requested", "sent", "skipped", "failed"]
SendFunc = Callable[..., Awaitable[object]]


@dataclass(frozen=True, slots=True)
class EmailSendRequest:
    to: str
    subject: str
    body: str
    structured_evidence: str | None = None
    conversation_id: str | None = None


@dataclass(frozen=True, slots=True)
class EmailSendResult:
    status: EmailSendStatus
    to: str | None = None
    message: str = ""

    def as_dict(self) -> dict[str, str | None]:
        return {
            "status": self.status,
            "to": self.to,
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class EmailSender:
    smtp_host: str
    smtp_port: int
    from_address: str
    from_name: str = "Orion"
    smtp_username: str = ""
    smtp_password: str = ""
    start_tls: bool = True
    timeout: float = 10.0
    send_func: SendFunc | None = None
    factory: EmailMessageFactory | None = None

    @classmethod
    def from_settings(
        cls,
        settings: OrionSettings,
        *,
        send_func: SendFunc | None = None,
        llm_provider: LLMProvider | None = None,
    ) -> "EmailSender":
        return cls(
            smtp_host=settings.email_smtp_host,
            smtp_port=settings.email_smtp_port,
            smtp_username=settings.email_smtp_username,
            smtp_password=settings.email_smtp_password,
            from_address=settings.email_from_address,
            from_name=settings.email_from_name,
            start_tls=settings.email_start_tls,
            timeout=settings.email_timeout,
            send_func=send_func,
            factory=EmailMessageFactory(provider=llm_provider),
        )

    async def send_response(self, request: EmailSendRequest) -> EmailSendResult:
        if not self.smtp_host.strip() or not self.from_address.strip():
            _LOG.info(
                "email_send skipped to=%s reason=missing_smtp_config host_present=%s from_present=%s",
                request.to,
                bool(self.smtp_host.strip()),
                bool(self.from_address.strip()),
            )
            return EmailSendResult(status="skipped", to=request.to, message="e-mail não configurado")

        message = EmailMessage()
        message["To"] = request.to
        message["From"] = formataddr((self.from_name, self.from_address))
        message["Subject"] = request.subject
        if request.conversation_id:
            message["X-Orion-Conversation-Id"] = request.conversation_id
        message.set_content(request.body, subtype="plain", charset="utf-8")
        report = await (self.factory or EmailMessageFactory()).build_report(
            subject=request.subject,
            body=request.body,
            from_name=self.from_name,
            structured_evidence=request.structured_evidence,
        )
        message.add_alternative(
            render_response_email_html(
                subject=request.subject,
                body=request.body,
                from_name=self.from_name,
                report=report,
            ),
            subtype="html",
            charset="utf-8",
        )

        send = self.send_func or _send_with_aiosmtplib
        try:
            _LOG.info(
                "email_send attempt to=%s smtp=%s:%s start_tls=%s auth=%s conversation_id=%s",
                request.to,
                self.smtp_host,
                self.smtp_port,
                self.start_tls,
                bool(self.smtp_username.strip()),
                request.conversation_id,
            )
            await send(
                message,
                hostname=self.smtp_host,
                port=self.smtp_port,
                username=self.smtp_username or None,
                password=self.smtp_password or None,
                start_tls=self.start_tls,
                timeout=self.timeout,
            )
        except Exception as exc:  # pragma: no cover - mensagem sanitizada é testada por fake
            error_detail = _safe_error_detail(
                exc,
                sensitive_values=(self.smtp_password, request.body),
            )
            _LOG.warning(
                "email_send failed to=%s smtp=%s:%s error_type=%s error_detail=%s",
                request.to,
                self.smtp_host,
                self.smtp_port,
                type(exc).__name__,
                error_detail,
            )
            return EmailSendResult(
                status="failed",
                to=request.to,
                message=f"falha ao enviar e-mail ({type(exc).__name__}: {error_detail})",
            )
        _LOG.info(
            "email_send sent to=%s smtp=%s:%s conversation_id=%s",
            request.to,
            self.smtp_host,
            self.smtp_port,
            request.conversation_id,
        )
        return EmailSendResult(status="sent", to=request.to, message="e-mail enviado")


async def _send_with_aiosmtplib(message: EmailMessage, **kwargs: object) -> object:
    import aiosmtplib

    return await aiosmtplib.send(message, **kwargs)


def _safe_error_detail(
    exc: Exception,
    *,
    sensitive_values: tuple[str | None, ...] = (),
    max_len: int = 300,
) -> str:
    detail = str(exc).strip() or repr(exc)
    for value in sensitive_values:
        if value:
            detail = detail.replace(value, "[redacted]")
    detail = re.sub(r"(?i)(password|senha|secret|token|api[_-]?key)=\S+", r"\1=[redacted]", detail)
    detail = re.sub(r"\s+", " ", detail).strip()
    if len(detail) > max_len:
        detail = detail[: max_len - 3].rstrip() + "..."
    return detail or type(exc).__name__

"""Envio assíncrono de respostas do chat por e-mail."""

from __future__ import annotations

import logging
import re
from base64 import b64encode
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr
from typing import Literal
from urllib.parse import urlencode
from urllib.request import Request, urlopen

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
    driver: str = "smtp"
    from_name: str = "Orion"
    mailgun_endpoint: str = "https://api.mailgun.net/v3"
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
            smtp_host=settings.effective_email_host,
            smtp_port=settings.effective_email_port,
            driver=settings.email_driver_name,
            smtp_username=settings.effective_email_username,
            smtp_password=settings.effective_email_password,
            from_address=settings.email_from_address,
            from_name=settings.effective_email_from_name,
            mailgun_endpoint=settings.effective_mailgun_endpoint,
            start_tls=settings.email_start_tls,
            timeout=settings.email_timeout,
            send_func=send_func,
            factory=EmailMessageFactory(provider=llm_provider),
        )

    async def send_response(self, request: EmailSendRequest) -> EmailSendResult:
        if not self.smtp_host.strip() or not self.from_address.strip():
            _LOG.info(
                "email_send skipped to=%s reason=missing_email_config driver=%s host_present=%s from_present=%s",
                request.to,
                self.driver,
                bool(self.smtp_host.strip()),
                bool(self.from_address.strip()),
            )
            return EmailSendResult(status="skipped", to=request.to, message="e-mail não configurado")

        if self.driver == "mailgun" and not self.smtp_password:
            _LOG.info(
                "email_send skipped to=%s reason=missing_mailgun_api_key domain_present=%s from_present=%s",
                request.to,
                bool(self.smtp_host.strip()),
                bool(self.from_address.strip()),
            )
            return EmailSendResult(status="skipped", to=request.to, message="e-mail não configurado")

        if self.driver == "mailgun":
            return await self._send_with_mailgun(request)

        return await self._send_with_smtp(request)

    async def _build_message_parts(self, request: EmailSendRequest) -> tuple[str, str, str]:
        from_header = formataddr((self.from_name, self.from_address))
        report = await (self.factory or EmailMessageFactory()).build_report(
            subject=request.subject,
            body=request.body,
            from_name=self.from_name,
            structured_evidence=request.structured_evidence,
        )
        html = render_response_email_html(
            subject=request.subject,
            body=request.body,
            from_name=self.from_name,
            report=report,
        )
        return from_header, request.body, html

    async def _send_with_smtp(self, request: EmailSendRequest) -> EmailSendResult:
        from_header, text_body, html_body = await self._build_message_parts(request)
        message = EmailMessage()
        message["To"] = request.to
        message["From"] = from_header
        message["Subject"] = request.subject
        if request.conversation_id:
            message["X-Orion-Conversation-Id"] = request.conversation_id
        message.set_content(text_body, subtype="plain", charset="utf-8")
        message.add_alternative(html_body, subtype="html", charset="utf-8")

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

    async def _send_with_mailgun(self, request: EmailSendRequest) -> EmailSendResult:
        from_header, text_body, html_body = await self._build_message_parts(request)
        data = {
            "from": from_header,
            "to": request.to,
            "subject": request.subject,
            "text": text_body,
            "html": html_body,
        }
        if request.conversation_id:
            data["h:X-Orion-Conversation-Id"] = request.conversation_id
        domain = self.smtp_host.strip().strip("/")
        url = f"{self.mailgun_endpoint.rstrip('/')}/{domain}/messages"
        auth_user = self.smtp_username.strip() or "api"
        send = self.send_func or _send_with_mailgun_api
        try:
            _LOG.info(
                "email_send attempt to=%s driver=mailgun domain=%s auth=%s conversation_id=%s",
                request.to,
                domain,
                bool(self.smtp_password),
                request.conversation_id,
            )
            await send(
                url=url,
                auth=(auth_user, self.smtp_password),
                data=data,
                timeout=self.timeout,
            )
        except Exception as exc:  # pragma: no cover - mensagem sanitizada é testada por fake
            error_detail = _safe_error_detail(
                exc,
                sensitive_values=(self.smtp_password, request.body),
            )
            _LOG.warning(
                "email_send failed to=%s driver=mailgun domain=%s error_type=%s error_detail=%s",
                request.to,
                domain,
                type(exc).__name__,
                error_detail,
            )
            return EmailSendResult(
                status="failed",
                to=request.to,
                message=f"falha ao enviar e-mail ({type(exc).__name__}: {error_detail})",
            )
        _LOG.info(
            "email_send sent to=%s driver=mailgun domain=%s conversation_id=%s",
            request.to,
            domain,
            request.conversation_id,
        )
        return EmailSendResult(status="sent", to=request.to, message="e-mail enviado")


async def _send_with_aiosmtplib(message: EmailMessage, **kwargs: object) -> object:
    import aiosmtplib

    return await aiosmtplib.send(message, **kwargs)


async def _send_with_mailgun_api(
    *,
    url: str,
    auth: tuple[str, str],
    data: dict[str, str],
    timeout: float,
) -> object:
    import asyncio

    def _post() -> object:
        username, password = auth
        encoded = urlencode(data).encode("utf-8")
        token = b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
        request = Request(
            url,
            data=encoded,
            headers={
                "Authorization": f"Basic {token}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )
        with urlopen(request, timeout=timeout) as response:
            return response.read()

    return await asyncio.to_thread(_post)


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

from __future__ import annotations

import logging
from email.message import EmailMessage
from pathlib import Path

from orion_mcp_v3.api.email import EmailSender, EmailSendRequest
from orion_mcp_v3.api.email.models import EmailReport, EmailSection
from orion_mcp_v3.config.settings import get_settings_uncached


FIXTURE = Path("tests/fixtures/email/fechamento_gerencial_marco.txt")


class CapturingFactory:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def build_report(self, **kwargs):  # type: ignore[no-untyped-def]
        self.calls.append(kwargs)
        return EmailReport(
            subject=str(kwargs["subject"]),
            from_name=str(kwargs["from_name"]),
            headline="Relatório estruturado",
            sections=(EmailSection(title="Evidência", kind="default"),),
        )


async def test_email_sender_sends_plain_text_response_with_settings() -> None:
    calls: list[tuple[EmailMessage, dict]] = []

    async def fake_send(message: EmailMessage, **kwargs):
        calls.append((message, kwargs))
        return {}

    settings = get_settings_uncached(
        email_enabled=True,
        email_smtp_host="smtp.local",
        email_smtp_port=1025,
        email_smtp_username="user",
        email_smtp_password="secret",
        email_from_address="orion@local.test",
        email_from_name="Orion",
        email_start_tls=False,
        email_timeout=3.5,
    )
    sender = EmailSender.from_settings(settings, send_func=fake_send)

    result = await sender.send_response(
        EmailSendRequest(
            to="destino@local.test",
            subject="Resposta Orion",
            body="Resposta gerada pelo chat",
            conversation_id="conv-1",
        )
    )

    assert result.status == "sent"
    assert result.to == "destino@local.test"
    assert len(calls) == 1
    message, kwargs = calls[0]
    assert message["To"] == "destino@local.test"
    assert message["From"] == "Orion <orion@local.test>"
    assert message["Subject"] == "Resposta Orion"
    assert message.is_multipart()
    plain = message.get_body(preferencelist=("plain",))
    html = message.get_body(preferencelist=("html",))
    assert plain is not None
    assert html is not None
    assert plain.get_content().strip() == "Resposta gerada pelo chat"
    assert "<!doctype html>" in html.get_content()
    assert "Resposta Orion" in html.get_content()
    assert "Resposta gerada pelo chat" in html.get_content()
    assert kwargs["hostname"] == "smtp.local"
    assert kwargs["port"] == 1025
    assert kwargs["username"] == "user"
    assert kwargs["password"] == "secret"
    assert kwargs["start_tls"] is False
    assert kwargs["timeout"] == 3.5


async def test_email_sender_builds_structured_html_from_report_text() -> None:
    calls: list[tuple[EmailMessage, dict]] = []

    async def fake_send(message: EmailMessage, **kwargs):
        calls.append((message, kwargs))
        return {}

    settings = get_settings_uncached(
        email_enabled=True,
        email_smtp_host="smtp.local",
        email_smtp_port=1025,
        email_from_address="orion@local.test",
        email_from_name="CarSoul",
        email_start_tls=False,
    )
    sender = EmailSender.from_settings(settings, send_func=fake_send)

    result = await sender.send_response(
        EmailSendRequest(
            to="destino@local.test",
            subject="Fechamento gerencial de março de 2026",
            body=FIXTURE.read_text(encoding="utf-8"),
            conversation_id="conv-fechamento",
        )
    )

    assert result.status == "sent"
    html_part = calls[0][0].get_body(preferencelist=("html",))
    assert html_part is not None
    html = html_part.get_content()
    assert 'class="hero-card"' in html
    assert "Faturamento por forma de pagamento" in html
    assert "Produção por serviço" in html
    assert "Discrepância a verificar" in html


async def test_email_sender_passes_structured_evidence_to_factory() -> None:
    calls: list[tuple[EmailMessage, dict]] = []

    async def fake_send(message: EmailMessage, **kwargs):
        calls.append((message, kwargs))
        return {}

    settings = get_settings_uncached(
        email_enabled=True,
        email_smtp_host="smtp.local",
        email_smtp_port=1025,
        email_from_address="orion@local.test",
        email_from_name="CarSoul",
        email_start_tls=False,
    )
    factory = CapturingFactory()
    sender = EmailSender.from_settings(settings, send_func=fake_send)
    sender = EmailSender(
        smtp_host=sender.smtp_host,
        smtp_port=sender.smtp_port,
        smtp_username=sender.smtp_username,
        smtp_password=sender.smtp_password,
        from_address=sender.from_address,
        from_name=sender.from_name,
        start_tls=sender.start_tls,
        timeout=sender.timeout,
        send_func=sender.send_func,
        factory=factory,  # type: ignore[arg-type]
    )

    result = await sender.send_response(
        EmailSendRequest(
            to="destino@local.test",
            subject="Fechamento gerencial",
            body="narrativa do chat",
            structured_evidence="## Faturamento por tipo de pagamento\n1. PIX: R$ 10,00",
            conversation_id="conv-evidence",
        )
    )

    assert result.status == "sent"
    assert factory.calls[0]["body"] == "narrativa do chat"
    assert factory.calls[0]["structured_evidence"] == "## Faturamento por tipo de pagamento\n1. PIX: R$ 10,00"


async def test_email_sender_returns_failed_without_leaking_body_or_password() -> None:
    async def fake_send(message: EmailMessage, **kwargs):
        raise RuntimeError("smtp exploded with secret")

    settings = get_settings_uncached(
        email_enabled=True,
        email_smtp_host="smtp.local",
        email_from_address="orion@local.test",
        email_smtp_password="secret",
    )
    sender = EmailSender.from_settings(settings, send_func=fake_send)

    result = await sender.send_response(
        EmailSendRequest(
            to="destino@local.test",
            subject="Resposta Orion",
            body="corpo sensivel",
        )
    )

    assert result.status == "failed"
    assert result.to == "destino@local.test"
    assert "smtp exploded" in result.message
    assert "corpo sensivel" not in result.message
    assert "secret" not in result.message


async def test_email_sender_logs_failure_detail_without_sensitive_data(caplog) -> None:
    async def fake_send(message: EmailMessage, **kwargs):
        raise RuntimeError("connect failed for secret with corpo sensivel")

    settings = get_settings_uncached(
        email_enabled=True,
        email_smtp_host="smtp.local",
        email_smtp_port=1025,
        email_from_address="orion@local.test",
        email_smtp_password="secret",
    )
    sender = EmailSender.from_settings(settings, send_func=fake_send)

    with caplog.at_level(logging.WARNING, logger="orion.api.email"):
        result = await sender.send_response(
            EmailSendRequest(
                to="destino@local.test",
                subject="Resposta Orion",
                body="corpo sensivel",
            )
        )

    messages = "\n".join(record.getMessage() for record in caplog.records)
    assert result.status == "failed"
    assert "connect failed" in result.message
    assert "connect failed" in messages
    assert "secret" not in result.message
    assert "secret" not in messages
    assert "corpo sensivel" not in result.message
    assert "corpo sensivel" not in messages


async def test_email_sender_logs_attempt_and_success_without_sensitive_data(caplog) -> None:
    async def fake_send(message: EmailMessage, **kwargs):
        return {}

    settings = get_settings_uncached(
        email_enabled=True,
        email_smtp_host="smtp.local",
        email_smtp_port=1025,
        email_from_address="orion@local.test",
        email_smtp_password="secret",
        email_start_tls=False,
    )
    sender = EmailSender.from_settings(settings, send_func=fake_send)

    with caplog.at_level(logging.INFO, logger="orion.api.email"):
        result = await sender.send_response(
            EmailSendRequest(
                to="destino@local.test",
                subject="Resposta Orion",
                body="corpo sensivel",
                conversation_id="conv-1",
            )
        )

    assert result.status == "sent"
    messages = "\n".join(record.getMessage() for record in caplog.records)
    assert "email_send attempt" in messages
    assert "email_send sent" in messages
    assert "smtp.local:1025" in messages
    assert "destino@local.test" in messages
    assert "secret" not in messages
    assert "corpo sensivel" not in messages

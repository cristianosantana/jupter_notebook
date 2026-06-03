from __future__ import annotations

import logging
from email.message import EmailMessage

from orion_mcp_v3.api.email_sender import EmailSender, EmailSendRequest
from orion_mcp_v3.config.settings import get_settings_uncached


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

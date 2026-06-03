from __future__ import annotations

import os
from uuid import uuid4

import pytest

from orion_mcp_v3.api.email_sender import EmailSender, EmailSendRequest
from orion_mcp_v3.config.settings import get_settings_uncached


async def test_configured_smtp_sends_email_from_env() -> None:
    if os.getenv("ORION_RUN_CONFIGURED_SMTP_TEST", "").strip().lower() not in {"1", "true", "yes"}:
        pytest.skip("defina ORION_RUN_CONFIGURED_SMTP_TEST=true para testar o SMTP real configurado")

    settings = get_settings_uncached()
    if not settings.email_configured:
        pytest.skip("ORION_EMAIL_* não está configurado para envio SMTP")

    token = uuid4().hex
    to = f"orion-test-{token}@local.test"
    subject = f"Teste Orion SMTP {token}"
    body = f"Mensagem de teste do Orion SMTP configurado. token={token}"

    result = await EmailSender.from_settings(settings).send_response(
        EmailSendRequest(
            to=to,
            subject=subject,
            body=body,
            conversation_id=f"test-{token}",
        )
    )

    assert result.status == "sent", result.as_dict()

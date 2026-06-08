from __future__ import annotations

import os
from uuid import uuid4

import pytest

from orion_mcp_v3.api.email_sender import EmailSender, EmailSendRequest
from orion_mcp_v3.config.settings import get_settings_uncached


async def test_configured_email_sends_email_from_env() -> None:
    settings = get_settings_uncached()
    driver = settings.email_driver_name
    driver_flag = f"ORION_RUN_CONFIGURED_{driver.upper()}_TEST"
    run_enabled = os.getenv("ORION_RUN_CONFIGURED_EMAIL_TEST", "").strip().lower() in {"1", "true", "yes"}
    run_enabled = run_enabled or os.getenv(driver_flag, "").strip().lower() in {"1", "true", "yes"}
    if not run_enabled:
        pytest.skip(f"defina {driver_flag}=true ou ORION_RUN_CONFIGURED_EMAIL_TEST=true para testar envio real")
    if not settings.email_configured:
        pytest.skip(f"ORION_EMAIL_* não está configurado para envio real via {driver}")

    token = uuid4().hex
    to = f"cristiano@carsoul.com.br"
    subject = f"Teste Orion {driver} {token}"
    body = f"Mensagem de teste do Orion via {driver}. token={token}"

    result = await EmailSender.from_settings(settings).send_response(
        EmailSendRequest(
            to=to,
            subject=subject,
            body=body,
            conversation_id=f"test-{token}",
        )
    )

    assert result.status == "sent", result.as_dict()

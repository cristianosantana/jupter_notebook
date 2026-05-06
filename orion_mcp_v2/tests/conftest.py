"""Evita dependência de Postgres/MySQL/Redis/OpenAI reais nos testes."""

from __future__ import annotations

import pytest

from orion_mcp_v2.config.settings import get_settings


@pytest.fixture(autouse=True)
def _neutral_external_services(monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("ORION_V2_DATABASE_URL", "")
    monkeypatch.setenv("ORION_V2_DB_REQUIRED", "false")
    monkeypatch.setenv("ORION_V2_MYSQL_URL", "")
    monkeypatch.setenv("ORION_V2_REDIS_URL", "")
    monkeypatch.setenv("ORION_V2_OPENAI_API_KEY", "")

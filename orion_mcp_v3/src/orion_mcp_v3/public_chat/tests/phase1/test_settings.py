from __future__ import annotations

from orion_mcp_v3.public_chat.config.settings import PublicChatSettings


def test_settings_from_env(monkeypatch) -> None:
    monkeypatch.setenv("PUBLIC_CHAT_POSTGRES_URL", "postgresql://u:p@localhost/db")
    monkeypatch.setenv("PUBLIC_CHAT_CONTEXT_DEPTH", "5")

    settings = PublicChatSettings.from_env()

    assert settings.postgres_enabled is True
    assert settings.postgres_url == "postgresql://u:p@localhost/db"
    assert settings.context_depth == 5


def test_settings_postgres_disabled_when_url_empty() -> None:
    settings = PublicChatSettings()
    assert settings.postgres_enabled is False

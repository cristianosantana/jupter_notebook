from __future__ import annotations

from orion_mcp_v3.public_chat.config.settings import PublicChatSettings


def test_settings_enabled_flags(monkeypatch) -> None:
    monkeypatch.setenv("PUBLIC_CHAT_ENABLED", "true")
    monkeypatch.setenv("PUBLIC_CHAT_USE_PRESENTATION_SNAPSHOT", "1")
    monkeypatch.setenv("PUBLIC_CHAT_POSTGRES_URL", "postgresql://u:p@localhost/db")
    monkeypatch.setenv("PUBLIC_CHAT_LLM_API_KEY", "sk-test")
    monkeypatch.setenv("PUBLIC_CHAT_EMBEDDING_API_KEY", "sk-test")

    settings = PublicChatSettings.from_env()

    assert settings.enabled is True
    assert settings.use_presentation_snapshot is True
    assert settings.runtime_ready is True


def test_settings_runtime_not_ready_when_disabled() -> None:
    settings = PublicChatSettings(
        enabled=False,
        postgres_url="postgresql://x",
        llm_api_key="sk",
        embedding_api_key="sk",
    )
    assert settings.runtime_ready is False

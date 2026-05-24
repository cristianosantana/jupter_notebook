"""Fase 7 — Configuração central: OrionSettings, get_settings, integração com módulos."""

from __future__ import annotations

import os

from orion_mcp_v3.config import OrionSettings, get_settings_uncached, ANALYTICS_ALLOWLIST


# ── 7.1 OrionSettings defaults ──────────────────────────────────────


def test_settings_defaults(monkeypatch) -> None:
    for key in list(os.environ):
        if key.startswith("ORION_"):
            monkeypatch.delenv(key, raising=False)
    s = get_settings_uncached()
    assert s.mysql_url == ""
    assert s.postgres_url == ""
    assert s.redis_url == ""
    assert s.max_tokens == 4096
    assert s.default_limit == 500
    assert s.llm_model == "gpt-5-mini"
    assert s.llm_max_tokens == 2048
    assert s.memory_window == 60
    assert s.default_policy == "analytical"
    assert s.api_port == 8000
    assert s.log_level == "INFO"


def test_settings_mysql_enabled() -> None:
    s = get_settings_uncached(mysql_url="mysql://u:p@h/db")
    assert s.mysql_enabled is True
    s2 = get_settings_uncached(mysql_url="")
    assert s2.mysql_enabled is False


def test_settings_postgres_enabled() -> None:
    s = get_settings_uncached(postgres_url="postgres://u:p@h/db")
    assert s.postgres_enabled is True


def test_settings_redis_enabled() -> None:
    s = get_settings_uncached(redis_url="redis://localhost:6379/0")
    assert s.redis_enabled is True


def test_settings_llm_enabled() -> None:
    s = get_settings_uncached(llm_api_key="sk-123")
    assert s.llm_enabled is True
    s2 = get_settings_uncached(llm_api_key="")
    assert s2.llm_enabled is False


def test_settings_cors_origins_list() -> None:
    s = get_settings_uncached(api_cors_origins="http://a.com, http://b.com")
    assert s.cors_origins_list == ["http://a.com", "http://b.com"]


def test_settings_cors_wildcard() -> None:
    s = get_settings_uncached(api_cors_origins="*")
    assert s.cors_origins_list == ["*"]


def test_settings_overrides() -> None:
    s = get_settings_uncached(
        max_tokens=8192,
        llm_model="gpt-5-mini",
        memory_window=100,
        default_policy="analytical",
    )
    assert s.max_tokens == 8192
    assert s.llm_model == "gpt-5-mini"
    assert s.memory_window == 100
    assert s.default_policy == "analytical"


def test_settings_timeouts() -> None:
    s = get_settings_uncached()
    assert s.mysql_timeout == 30.0
    assert s.postgres_timeout == 30.0
    assert s.redis_timeout == 5.0
    assert s.llm_timeout == 60.0


def test_settings_pool_sizes() -> None:
    s = get_settings_uncached(mysql_pool_min=2, mysql_pool_max=20)
    assert s.mysql_pool_min == 2
    assert s.mysql_pool_max == 20


def test_settings_log_and_trace() -> None:
    s = get_settings_uncached(log_level="DEBUG", trace_enabled=True)
    assert s.log_level == "DEBUG"
    assert s.trace_enabled is True


def test_settings_analytics_pipeline_trace_default(monkeypatch) -> None:
    monkeypatch.delenv("ORION_ANALYTICS_PIPELINE_TRACE", raising=False)
    monkeypatch.delenv("ORION_ANALYTICS_PIPELINE_LOG_DIR", raising=False)
    s = get_settings_uncached()
    assert s.analytics_pipeline_trace is False
    assert s.analytics_pipeline_log_dir == ""


def test_settings_analytics_pipeline_trace_from_env(monkeypatch) -> None:
    monkeypatch.setenv("ORION_ANALYTICS_PIPELINE_TRACE", "true")
    s = get_settings_uncached()
    assert s.analytics_pipeline_trace is True


    monkeypatch.setenv("ORION_MYSQL_URL", "mysql://test:pass@db:3306/orion")
    monkeypatch.setenv("ORION_MAX_TOKENS", "16000")
    monkeypatch.setenv("ORION_LLM_MODEL", "claude-4")
    s = get_settings_uncached()
    assert s.mysql_url == "mysql://test:pass@db:3306/orion"
    assert s.max_tokens == 16000
    assert s.llm_model == "claude-4"


def test_settings_api_debug_from_env(monkeypatch) -> None:
    monkeypatch.setenv("ORION_API_DEBUG", "true")
    s = get_settings_uncached()
    assert s.api_debug is True


# ── Integração: allowlist ainda funciona ─────────────────────────────


def test_analytics_allowlist_unchanged() -> None:
    assert "os" in ANALYTICS_ALLOWLIST.tables
    assert "clientes" in ANALYTICS_ALLOWLIST.tables


# ── Integração: create_app usa settings ──────────────────────────────


def test_create_app_with_custom_settings() -> None:
    from fastapi.testclient import TestClient
    from orion_mcp_v3.api.main import create_app

    s = get_settings_uncached(max_tokens=2048, memory_window=10)
    app = create_app(settings=s)
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200

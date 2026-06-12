"""
Garante que o executor injectado apenas no lifespan (fluxo produção / uvicorn)
é visível na rota de chat e produz evidência nos safeguards.

O caminho alternativo (analytics_executor passado a create_app) já é coberto
em test_api_phase6; aqui simula-se create_mysql_pool sem base real.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from orion_mcp_v3.api.main import create_app
from orion_mcp_v3.config.settings import get_settings, get_settings_uncached
from orion_mcp_v3.protocols.llm import EchoLLMProvider


_MOCK_FORMAS = [
    {
        "forma_pagamento": "pix",
        "qtd_recebimentos": 150,
        "total_recebido": 85000.0,
        "ticket_medio": 566.67,
        "percentual_total": 45.5,
    },
    {
        "forma_pagamento": "cartao credito",
        "qtd_recebimentos": 100,
        "total_recebido": 62000.0,
        "ticket_medio": 620.0,
        "percentual_total": 33.2,
    },
]


class _FakeCursor:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    async def execute(self, query: str, params: object = None) -> None:
        self._last_query = query

    async def fetchall(self) -> list[dict]:
        return list(self._rows)


class _FakeCursorCM:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    async def __aenter__(self) -> _FakeCursor:
        return _FakeCursor(self._rows)

    async def __aexit__(self, *args: object) -> None:
        return None


class _FakeConn:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    async def execute(self, query: str, params: object = None) -> None:
        """Mock do método execute para compatibilidade com timeout."""
        # Apenas ignora a chamada (não precisamos do timeout no teste)
        pass

    def cursor(self, cursor_cls: object | None = None) -> _FakeCursorCM:
        return _FakeCursorCM(self._rows)


class _FakeAcquire:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    async def __aenter__(self) -> _FakeConn:
        return _FakeConn(self._rows)

    async def __aexit__(self, *args: object) -> None:
        return None


class _FakePool:
    """Compatível com MysqlDatastoreClient: acquire(), close(), wait_closed()."""

    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    def acquire(self) -> _FakeAcquire:
        return _FakeAcquire(self._rows)

    def close(self) -> None:
        pass

    async def wait_closed(self) -> None:
        pass


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_chat_analytics_executor_from_lifespan_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sem analytics_executor em create_app: pool fake no lifespan → evidência na resposta."""

    async def fake_create_mysql_pool(url: str | None, **kwargs: object) -> _FakePool:
        return _FakePool(_MOCK_FORMAS)

    async def fake_close_mysql_pool(pool: object | None) -> None:
        return None

    monkeypatch.setattr(
        "orion_mcp_v3.connection_hub.pools.create_mysql_pool",
        fake_create_mysql_pool,
    )
    monkeypatch.setattr(
        "orion_mcp_v3.connection_hub.pools.close_mysql_pool",
        fake_close_mysql_pool,
    )

    settings = get_settings_uncached(
        mysql_url="mysql://user:pass@127.0.0.1:3306/testdb",
        _env_file=None,
    )
    app = create_app(
        settings=settings,
        llm_provider=EchoLLMProvider(),
    )
    # Starlette: o lifespan só corre com ``with TestClient(app)`` — sem isto o pool
    # nunca é criado e o executor permanece ausente (falso negativo em testes).
    with TestClient(app) as client:
        r = client.post(
            "/api/v1/chat",
            json={"message": "Qual forma de pagamento domina o faturamento entre janeiro e abril de 2026?"},
        )
        assert r.status_code == 200
        meta = r.json()["meta"]
        safeguards = meta.get("safeguards", [])
        assert "no_evidence" not in safeguards, safeguards
        assert "evidence_cited" in safeguards
        assert "coverage_note_injected" in safeguards

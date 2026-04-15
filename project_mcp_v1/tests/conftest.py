"""Fixtures partilhados — evita contactar MySQL para o glossário em testes."""

import pytest


@pytest.fixture(autouse=True)
def disable_entity_glossary_for_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENTITY_GLOSSARY_ENABLED", "false")
    from app.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def orchestrator_flow_legacy_for_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fakes de LLM contam chamadas; ``fast_skeleton`` no .env local quebraria asserts."""
    monkeypatch.setenv("ORCHESTRATOR_FLOW_MODE", "legacy")
    from app.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()

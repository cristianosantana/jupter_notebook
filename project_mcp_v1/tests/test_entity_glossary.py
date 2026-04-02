"""Testes unitários do glossário de dimensões."""

from app.entity_glossary import _primeiro_nome_display


def test_primeiro_nome_display_first_token() -> None:
    assert _primeiro_nome_display("Maria Silva") == "Maria"
    assert _primeiro_nome_display("  João  Costa  ") == "João"


def test_primeiro_nome_display_single_word_and_empty() -> None:
    assert _primeiro_nome_display("AUDI") == "AUDI"
    assert _primeiro_nome_display("") == ""
    assert _primeiro_nome_display(None) == ""

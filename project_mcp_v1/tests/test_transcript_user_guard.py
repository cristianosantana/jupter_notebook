"""Garantia de mensagem user no transcript persistido (process_chat / UI fallback)."""

from __future__ import annotations

from app.main import ensure_transcript_includes_user_message


def test_ensure_transcript_inserts_user_when_missing():
    msgs: list[dict] = [
        {"role": "assistant", "content": "Olá"},
        {"role": "tool", "content": "{}"},
    ]
    assert ensure_transcript_includes_user_message(msgs, "  Qual o total?  ") is True
    assert msgs[0] == {"role": "user", "content": "Qual o total?"}
    assert msgs[1]["role"] == "assistant"


def test_ensure_transcript_noop_when_user_exists():
    msgs = [{"role": "user", "content": "já existe"}]
    assert ensure_transcript_includes_user_message(msgs, "outro") is False
    assert len(msgs) == 1


def test_ensure_transcript_noop_empty_text():
    msgs = [{"role": "assistant", "content": "x"}]
    assert ensure_transcript_includes_user_message(msgs, "   ") is False
    assert len(msgs) == 1


def test_ensure_transcript_detects_user_case_insensitive_role():
    msgs = [{"role": "User", "content": "x"}]
    assert ensure_transcript_includes_user_message(msgs, "y") is False

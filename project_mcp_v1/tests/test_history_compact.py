"""Histórico compacto para o payload ao LLM."""

import asyncio

from app.config import Settings
from app.history_payload import build_compact_history_messages_for_llm, latest_user_text_for_semantic


def test_latest_user_text_skips_synthetic():
    msgs = [
        {"role": "user", "content": "### Resumo", "_orch_synthetic": True},
        {"role": "user", "content": "pergunta real"},
    ]
    assert latest_user_text_for_semantic(msgs) == "pergunta real"


def test_compact_disabled_returns_copy():
    async def _run():
        st = Settings.model_construct(orchestrator_history_compact_enabled=False)
        raw = [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}]
        out, note = await build_compact_history_messages_for_llm(
            raw,
            {},
            embed_texts=None,
            query_fallback="q",
            settings=st,
        )
        assert note == "compact_disabled"
        assert len(out) == 2
        assert out is not raw and out[0]["content"] == "a"

    asyncio.run(_run())


def test_compact_tail_and_summary_prefix():
    async def _run():
        st = Settings.model_construct(
            orchestrator_history_compact_enabled=True,
            orchestrator_history_tail_messages=2,
            orchestrator_history_semantic_enabled=False,
            memory_conversation_summary_enabled=True,
        )
        meta = {"conversation_summary": "Resumo curto."}
        msgs = [
            {"role": "user", "content": "m1"},
            {"role": "assistant", "content": "a1"},
            {"role": "user", "content": "m2"},
            {"role": "assistant", "content": "a2"},
        ]
        out, note = await build_compact_history_messages_for_llm(
            msgs,
            meta,
            embed_texts=None,
            query_fallback="m2",
            settings=st,
        )
        assert note == "ok"
        assert out[0].get("_orch_synthetic")
        assert "Resumo curto" in out[0]["content"]
        assert out[-2]["content"] == "m2"
        assert out[-1]["content"] == "a2"

    asyncio.run(_run())

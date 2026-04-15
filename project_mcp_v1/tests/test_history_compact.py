"""Histórico compacto para o payload ao LLM."""

import asyncio

from app.config import Settings
from app.history_payload import (
    build_compact_history_messages_for_llm,
    compute_safe_history_tail_start,
    latest_user_text_for_semantic,
)


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


def test_compute_safe_history_tail_start_expands_for_tool_pair():
    msgs = [
        {"role": "user", "content": "u0"},
        {"role": "assistant", "content": "a0"},
        {"role": "user", "content": "u1"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "c1",
                    "type": "function",
                    "function": {"name": "t", "arguments": "{}"},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "c1", "content": "{}"},
    ]
    start = compute_safe_history_tail_start(msgs, tail_n=2)
    assert msgs[start]["role"] == "assistant"
    assert msgs[start + 1]["role"] == "tool"


def test_compact_tail_preserves_assistant_tool_pair():
    async def _run():
        st = Settings.model_construct(
            orchestrator_history_compact_enabled=True,
            orchestrator_history_tail_messages=2,
            orchestrator_history_semantic_enabled=False,
            memory_conversation_summary_enabled=False,
        )
        msgs = [
            {"role": "user", "content": "u0"},
            {"role": "assistant", "content": "a0"},
            {"role": "user", "content": "u1"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "c1",
                        "type": "function",
                        "function": {"name": "t", "arguments": "{}"},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "c1", "content": '{"ok":true}'},
        ]
        out, note = await build_compact_history_messages_for_llm(
            msgs,
            {},
            embed_texts=None,
            query_fallback="u1",
            settings=st,
        )
        assert note == "ok"
        assert out[-2]["role"] == "assistant"
        assert out[-1]["role"] == "tool"

    asyncio.run(_run())

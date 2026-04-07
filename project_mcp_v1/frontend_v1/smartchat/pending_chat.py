"""Pedido POST /api/chat em thread + finalização (Parar / Editar)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any, Literal

import streamlit as st

from smartchat.schemas import ChatMessageAssistant, ChatMessageUser
from smartchat.services.api import ApiError, post_chat
from smartchat.state import (
    KEY_AGENT_USED,
    KEY_CHAT_DISCARD,
    KEY_CHAT_FUTURE,
    KEY_CHAT_INPUT,
    KEY_CHAT_LAST_TEXT,
    KEY_CHAT_REQ_SOURCE,
    KEY_EMPTY_PROMPT,
    KEY_ERROR,
    KEY_SESSION_ID,
    KEY_TRACE_RUN_ID,
    append_message,
    clear_pending_chat,
    get_messages,
    set_messages,
)

SourceKey = Literal["main", "empty"]

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="smartchat_chat")


def _post_worker(
    text: str,
    session_id: str | None,
    agent: str | None,
    trace_run_id: str | None,
) -> dict[str, Any]:
    return post_chat(
        text,
        session_id=session_id,
        target_agent=agent,
        trace_run_id=trace_run_id,
    )


def chat_future_pending() -> bool:
    fut = st.session_state.get(KEY_CHAT_FUTURE)
    return fut is not None and not fut.done()


def start_chat_job(text: str, source: SourceKey) -> None:
    """Adiciona mensagem do utilizador e inicia POST em background."""
    sid = st.session_state[KEY_SESSION_ID]
    agent = st.session_state[KEY_AGENT_USED]
    trace = st.session_state[KEY_TRACE_RUN_ID]

    append_message(ChatMessageUser(role="user", content=text))
    st.session_state[KEY_CHAT_LAST_TEXT] = text
    st.session_state[KEY_CHAT_REQ_SOURCE] = source
    st.session_state[KEY_CHAT_DISCARD] = False
    st.session_state[KEY_ERROR] = None

    fut = _executor.submit(_post_worker, text, sid, agent, trace)
    st.session_state[KEY_CHAT_FUTURE] = fut


def try_finalize_chat_future() -> bool:
    """Se o pedido terminou, aplica resposta ou erro. Devolve True se consumiu um future."""
    fut = st.session_state.get(KEY_CHAT_FUTURE)
    if fut is None or not fut.done():
        return False

    del st.session_state[KEY_CHAT_FUTURE]
    discard = bool(st.session_state.pop(KEY_CHAT_DISCARD, False))

    try:
        res = fut.result(timeout=0)
    except ApiError as ex:
        if discard:
            return True
        msgs = get_messages()
        if msgs and msgs[-1].role == "user":
            msgs.pop()
            set_messages(msgs)
        st.session_state[KEY_ERROR] = str(ex)
        return True
    except Exception as ex:  # noqa: BLE001 — último recurso na UI
        if discard:
            return True
        msgs = get_messages()
        if msgs and msgs[-1].role == "user":
            msgs.pop()
            set_messages(msgs)
        st.session_state[KEY_ERROR] = str(ex)
        return True

    if discard:
        return True

    reply = res.get("reply") or ""
    cb = res.get("content_blocks")
    if cb is not None and not isinstance(cb, dict):
        cb = None
    append_message(ChatMessageAssistant(role="assistant", content=reply, content_blocks=cb))

    if res.get("session_id"):
        st.session_state[KEY_SESSION_ID] = str(res["session_id"])
    tid = res.get("trace_run_id")
    st.session_state[KEY_TRACE_RUN_ID] = str(tid).strip() if tid else None
    if res.get("agent_used"):
        st.session_state[KEY_AGENT_USED] = res["agent_used"]
    st.session_state[KEY_ERROR] = None
    return True


def stop_pending() -> None:
    """Ignora a resposta quando o pedido terminar; mantém a pergunta visível."""
    st.session_state[KEY_CHAT_DISCARD] = True


def edit_pending() -> None:
    """Remove a pergunta da conversa, repõe o texto no campo e liberta o pedido (resposta ignorada)."""
    msgs = get_messages()
    text = st.session_state.get(KEY_CHAT_LAST_TEXT) or ""
    if msgs and msgs[-1].role == "user":
        text = msgs[-1].content
        msgs.pop()
        set_messages(msgs)

    src = st.session_state.get(KEY_CHAT_REQ_SOURCE, "main")
    if src == "empty":
        st.session_state[KEY_EMPTY_PROMPT] = text
    else:
        st.session_state[KEY_CHAT_INPUT] = text

    clear_pending_chat()

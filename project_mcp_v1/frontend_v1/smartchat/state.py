"""Estado da sessão Streamlit."""

from __future__ import annotations

from typing import Any

import streamlit as st

from smartchat.schemas import ChatMessage, ChatMessageAssistant, ChatMessageUser

KEY_MESSAGES = "sc_messages"
KEY_SESSION_ID = "sc_session_id"
KEY_TRACE_RUN_ID = "sc_trace_run_id"
KEY_AGENT_USED = "sc_agent_used"
KEY_ERROR = "sc_error"
KEY_SESSIONS = "sc_sessions_list"
KEY_SESSIONS_LOADED = "sc_sessions_loaded"
KEY_PERSISTENCE = "sc_persistence_enabled"
KEY_EMPTY_PROMPT = "sc_empty_prompt"
KEY_PENDING_EMPTY_FILL = "sc_pending_empty_fill"
KEY_CLEAR_EMPTY_PROMPT = "sc_clear_empty_prompt"
KEY_TOPIC_PICK = "sc_topic_pick"
KEY_CHAT_INPUT = "sc_chat_input"
KEY_CHAT_FUTURE = "sc_chat_future"
KEY_CHAT_DISCARD = "sc_chat_discard_result"
KEY_CHAT_REQ_SOURCE = "sc_chat_req_source"
KEY_CHAT_LAST_TEXT = "sc_chat_last_text"


def init_state() -> None:
    if KEY_MESSAGES not in st.session_state:
        st.session_state[KEY_MESSAGES] = []
    if KEY_SESSION_ID not in st.session_state:
        st.session_state[KEY_SESSION_ID] = None
    if KEY_TRACE_RUN_ID not in st.session_state:
        st.session_state[KEY_TRACE_RUN_ID] = None
    if KEY_AGENT_USED not in st.session_state:
        st.session_state[KEY_AGENT_USED] = None
    if KEY_ERROR not in st.session_state:
        st.session_state[KEY_ERROR] = None
    if KEY_SESSIONS not in st.session_state:
        st.session_state[KEY_SESSIONS] = []
    if KEY_SESSIONS_LOADED not in st.session_state:
        st.session_state[KEY_SESSIONS_LOADED] = False
    if KEY_PERSISTENCE not in st.session_state:
        st.session_state[KEY_PERSISTENCE] = True
    if KEY_EMPTY_PROMPT not in st.session_state:
        st.session_state[KEY_EMPTY_PROMPT] = ""
    if KEY_TOPIC_PICK not in st.session_state:
        st.session_state[KEY_TOPIC_PICK] = None
    if KEY_CHAT_INPUT not in st.session_state:
        st.session_state[KEY_CHAT_INPUT] = ""
    if KEY_CHAT_DISCARD not in st.session_state:
        st.session_state[KEY_CHAT_DISCARD] = False


def clear_pending_chat() -> None:
    st.session_state.pop(KEY_CHAT_FUTURE, None)
    st.session_state.pop(KEY_CHAT_LAST_TEXT, None)
    st.session_state[KEY_CHAT_DISCARD] = False


def reset_conversation() -> None:
    clear_pending_chat()
    st.session_state[KEY_MESSAGES] = []
    st.session_state[KEY_SESSION_ID] = None
    st.session_state[KEY_TRACE_RUN_ID] = None
    st.session_state[KEY_AGENT_USED] = None
    st.session_state[KEY_ERROR] = None
    st.session_state[KEY_EMPTY_PROMPT] = ""
    st.session_state.pop(KEY_PENDING_EMPTY_FILL, None)
    st.session_state.pop(KEY_CLEAR_EMPTY_PROMPT, None)
    st.session_state[KEY_TOPIC_PICK] = None
    st.session_state[KEY_CHAT_INPUT] = ""


def get_messages() -> list[ChatMessage]:
    return st.session_state[KEY_MESSAGES]


def append_message(msg: ChatMessage) -> None:
    st.session_state[KEY_MESSAGES].append(msg)


def set_messages(msgs: list[ChatMessage]) -> None:
    st.session_state[KEY_MESSAGES] = msgs


def content_to_string(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    try:
        import json

        return json.dumps(content, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(content)


def map_stored_messages(raw: list[dict[str, Any]]) -> list[ChatMessage]:
    out: list[ChatMessage] = []
    for m in raw:
        r = m.get("role") or "user"
        c = content_to_string(m.get("content"))
        if r == "tool":
            continue
        if r == "user":
            out.append(ChatMessageUser(role="user", content=c))
        elif r == "assistant":
            cb = m.get("content_blocks")
            if cb is not None and not isinstance(cb, dict):
                cb = None
            out.append(ChatMessageAssistant(role="assistant", content=c, content_blocks=cb))
        else:
            out.append(ChatMessageAssistant(role="assistant", content=f"[{r}] {c}", content_blocks=None))
    return out


def load_session_from_api(session_id: str) -> None:
    from smartchat.services.api import get_session

    data = get_session(session_id)
    st.session_state[KEY_PERSISTENCE] = data.get("persistence_enabled", True)
    sess = data.get("session") or {}
    st.session_state[KEY_SESSION_ID] = str(sess.get("session_id") or session_id)
    tr = data.get("trace_run_id")
    st.session_state[KEY_TRACE_RUN_ID] = str(tr).strip() if tr else None
    st.session_state[KEY_AGENT_USED] = sess.get("current_agent")
    raw_msgs = data.get("messages") or []
    if isinstance(raw_msgs, list):
        set_messages(map_stored_messages([m for m in raw_msgs if isinstance(m, dict)]))
    else:
        set_messages([])
    st.session_state[KEY_ERROR] = None
    clear_pending_chat()

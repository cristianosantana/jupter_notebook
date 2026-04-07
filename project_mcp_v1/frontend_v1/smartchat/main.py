"""Orquestração da app Streamlit (``app.py`` permanece fino)."""

from __future__ import annotations

import streamlit as st

from smartchat.config import PAGE_ICON, PAGE_TITLE
from smartchat.pending_chat import try_finalize_chat_future
from smartchat.state import KEY_SESSION_ID, get_messages, init_state
from smartchat.styles import inject_styles
from smartchat.views.chat import render_main_chat
from smartchat.views.empty_state import render_empty_state
from smartchat.views.sidebar import render_sidebar


def run_app() -> None:
    st.set_page_config(
        page_title=PAGE_TITLE,
        page_icon=PAGE_ICON,
        layout="wide",
        initial_sidebar_state="expanded",
    )
    inject_styles()
    init_state()
    try_finalize_chat_future()
    render_sidebar()

    msgs = get_messages()
    sid = st.session_state[KEY_SESSION_ID]

    if len(msgs) == 0 and not sid:
        render_empty_state()
    elif len(msgs) == 0 and sid:
        st.info(
            "Esta sessão ainda não tem mensagens de especialista persistidas "
            "(o roteamento do Maestro não é guardado na base). Pode continuar a conversa abaixo."
        )
        render_main_chat()
    else:
        render_main_chat()

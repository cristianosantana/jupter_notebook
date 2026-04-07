"""Área principal: envio POST /api/chat e histórico."""

from __future__ import annotations

from datetime import timedelta

import streamlit as st

from smartchat.pending_chat import (
    chat_future_pending,
    edit_pending,
    start_chat_job,
    stop_pending,
    try_finalize_chat_future,
)
from smartchat.state import KEY_CHAT_DISCARD, KEY_CHAT_FUTURE, KEY_CHAT_INPUT, KEY_ERROR, get_messages
from smartchat.views.assistant_message import render_assistant_message


def _pending_poll_inner() -> None:
    fut = st.session_state.get(KEY_CHAT_FUTURE)
    if fut is None:
        return
    if fut.done():
        if try_finalize_chat_future():
            st.rerun()
        return

    if st.session_state.get(KEY_CHAT_DISCARD):
        st.warning("Pedido ainda em curso no servidor — a resposta será **ignorada** quando terminar (Parar).")
    else:
        st.info("A aguardar resposta do assistente…")
    c1, c2 = st.columns(2)
    with c1:
        if st.button(
            "Parar",
            key="sc_btn_stop",
            help="Ignora a resposta quando o servidor responder; mantém a sua pergunta visível.",
        ):
            stop_pending()
            try:
                st.toast("Quando o pedido terminar, a resposta será ignorada.")
            except AttributeError:
                pass
            st.rerun()
    with c2:
        if st.button(
            "Editar pergunta",
            key="sc_btn_edit",
            help="Remove a pergunta da conversa e repõe o texto no campo para alterar.",
        ):
            edit_pending()
            st.rerun()


try:
    _pending_poll = st.fragment(run_every=timedelta(milliseconds=450))(_pending_poll_inner)
except (TypeError, AttributeError):
    _pending_poll = _pending_poll_inner


def _render_chat_input_form(form_key: str, text_key: str, placeholder: str) -> bool:
    """Devolve True se o utilizador submeteu texto não vazio."""
    with st.form(form_key):
        st.text_area(
            "Mensagem",
            height=120,
            key=text_key,
            placeholder=placeholder,
            label_visibility="collapsed",
        )
        st.caption("Enter no teclado não envia automaticamente — use o botão Enviar.")
        sub = st.form_submit_button("Enviar", type="primary")
    if not sub:
        return False
    raw = (st.session_state.get(text_key) or "").strip()
    if not raw:
        return False
    st.session_state[text_key] = ""
    start_chat_job(raw, "main")
    return True


def render_main_chat() -> None:
    msgs = get_messages()
    for msg in msgs:
        if msg.role == "user":
            with st.chat_message("user"):
                st.markdown(msg.content)
        else:
            with st.chat_message("assistant"):
                render_assistant_message(msg.content, msg.content_blocks)

    err = st.session_state.get(KEY_ERROR)
    if err:
        st.error(err)

    if chat_future_pending():
        _pending_poll()
        st.caption("Aguarde o fim do pedido ou use **Parar** / **Editar**.")
        return

    if _render_chat_input_form(
        "main_chat_form",
        KEY_CHAT_INPUT,
        "Escreva a sua pergunta…",
    ):
        st.rerun()

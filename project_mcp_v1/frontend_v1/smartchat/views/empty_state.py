"""Hero, compositor inicial e tópicos em Vertical Card Stack / Stacked Scroll (CSS em ``custom.css``)."""

from __future__ import annotations

import streamlit as st

from smartchat.state import (
    KEY_CLEAR_EMPTY_PROMPT,
    KEY_EMPTY_PROMPT,
    KEY_ERROR,
    KEY_PENDING_EMPTY_FILL,
)
from smartchat.topics import EMPTY_STATE_TOPICS, EmptyStateTopic, topic_card_preview
from smartchat.pending_chat import start_chat_job


def _topic_button_label(topic: EmptyStateTopic) -> str:
    """Cartão compacto: título + pré-visualização (o texto completo preenche o prompt ao clicar)."""
    body = topic_card_preview(topic.text, max_len=120)
    return f"{topic.icon} {topic.title}\n{body}"


def render_empty_state() -> None:
    if st.session_state.pop(KEY_CLEAR_EMPTY_PROMPT, False):
        st.session_state[KEY_EMPTY_PROMPT] = ""

    _pending = st.session_state.pop(KEY_PENDING_EMPTY_FILL, None)
    if _pending is not None:
        st.session_state[KEY_EMPTY_PROMPT] = _pending

    err = st.session_state.get(KEY_ERROR)
    if err:
        st.error(err)

    st.markdown('<p class="sc-hero-title">Em que posso ajudar?</p>', unsafe_allow_html=True)
    st.markdown(
        '<p class="sc-hero-sub">Análises sobre OS, faturamento, vendedores e concessionárias — '
        "alinhado ao catálogo de ferramentas do assistente.</p>",
        unsafe_allow_html=True,
    )

    with st.form("empty_compose"):
        st.text_area(
            "Mensagem",
            height=160,
            key=KEY_EMPTY_PROMPT,
            placeholder="Peça uma análise, cole contexto ou escolha um cartão abaixo…",
            label_visibility="hidden",
        )
        st.caption("Enter não envia — use o botão Enviar.")
        _spacer, btn_col = st.columns([4, 1])
        with btn_col:
            sub = st.form_submit_button("Enviar", type="primary", use_container_width=True)

    if sub:
        text = (st.session_state.get(KEY_EMPTY_PROMPT) or "").strip()
        if text:
            start_chat_job(text, "empty")
            st.session_state[KEY_CLEAR_EMPTY_PROMPT] = True
            st.rerun()

    st.markdown(
        '<p class="sc-topics-heading">Perguntas sugeridas — deslize a pilha: os cartões parecem empilhados e '
        "vão travando no topo; clique para colocar o texto completo na mensagem.</p>",
        unsafe_allow_html=True,
    )

    _pad_l, stack_mid, _pad_r = st.columns([2, 3, 2])
    with stack_mid:
        with st.container(border=True):
            for topic in EMPTY_STATE_TOPICS:
                if st.button(
                    _topic_button_label(topic),
                    key=f"empty_topic_{topic.id}",
                    use_container_width=True,
                ):
                    st.session_state[KEY_PENDING_EMPTY_FILL] = topic.text
                    st.rerun()

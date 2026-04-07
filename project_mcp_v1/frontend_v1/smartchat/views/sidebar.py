"""Sidebar: nova conversa, lista de sessões, meta."""

from __future__ import annotations

from datetime import datetime
from html import escape

import streamlit as st

from smartchat.services.api import ApiError, list_sessions
from smartchat.state import (
    KEY_AGENT_USED,
    KEY_ERROR,
    KEY_PERSISTENCE,
    KEY_SESSIONS,
    KEY_SESSIONS_LOADED,
    KEY_SESSION_ID,
    KEY_TRACE_RUN_ID,
    load_session_from_api,
    reset_conversation,
)


def _short_id(uuid: str | None) -> str:
    if not uuid:
        return "Aguardando primeira msg…"
    return str(uuid)[:8]


def _format_when(iso: str | None) -> str:
    if not iso:
        return "—"
    try:
        d = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return d.strftime("%d %b %Y, %H:%M")
    except ValueError:
        return iso


def render_sidebar() -> None:
    st.sidebar.markdown("## 🤖 SmartChat")

    if st.sidebar.button("+ Nova conversa", use_container_width=True, type="primary"):
        reset_conversation()
        st.session_state[KEY_SESSIONS_LOADED] = False
        st.rerun()

    if st.sidebar.button("Actualizar lista de sessões", use_container_width=True):
        st.session_state[KEY_SESSIONS_LOADED] = False
        st.rerun()

    if not st.session_state[KEY_SESSIONS_LOADED]:
        try:
            data = list_sessions()
            st.session_state[KEY_SESSIONS] = data.get("sessions") or []
            st.session_state[KEY_PERSISTENCE] = data.get("persistence_enabled", True)
            st.session_state[KEY_SESSIONS_LOADED] = True
        except ApiError as ex:
            st.sidebar.error(f"Não foi possível listar sessões: {ex}")

    sessions = st.session_state[KEY_SESSIONS]
    if not st.session_state[KEY_PERSISTENCE]:
        st.sidebar.caption("Persistência inactiva: não há sessões guardadas na API.")
    elif sessions:
        st.sidebar.subheader("Histórico")

        def _label(sid: str) -> str:
            row = next((s for s in sessions if s.get("session_id") == sid), None)
            la = (row or {}).get("last_active_at")
            return f"{sid[:8]}… · {_format_when(la)}"

        sel_placeholder = "— Selecionar —"
        options = [sel_placeholder] + [str(s["session_id"]) for s in sessions]
        choice = st.sidebar.selectbox(
            "Sessão guardada",
            options,
            format_func=lambda x: x if x == sel_placeholder else _label(x),
            label_visibility="collapsed",
        )
        if st.sidebar.button("Abrir sessão selecionada", use_container_width=True):
            if choice and choice != sel_placeholder:
                try:
                    load_session_from_api(choice)
                    st.session_state[KEY_ERROR] = None
                except ApiError as ex:
                    st.session_state[KEY_ERROR] = str(ex)
                st.rerun()

    st.sidebar.divider()
    st.sidebar.markdown(
        '<p class="sc-sidebar-meta-heading">Meta da conversa actual</p>',
        unsafe_allow_html=True,
    )
    ag = st.session_state[KEY_AGENT_USED] or "—"
    st.sidebar.markdown(
        '<div class="sc-sidebar-meta">'
        f"<p><strong>Sessão:</strong> <code>{escape(_short_id(st.session_state[KEY_SESSION_ID]))}</code></p>"
        f"<p><strong>Trace:</strong> <code>{escape(_short_id(st.session_state[KEY_TRACE_RUN_ID]))}</code></p>"
        f"<p><strong>Agente:</strong> <code>{escape(str(ag))}</code></p>"
        "<p class=\"sc-sidebar-meta-hint\"><strong>target_agent</strong> — eco do último agente usado na API.</p>"
        "</div>",
        unsafe_allow_html=True,
    )

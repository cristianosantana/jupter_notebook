"""Injeta CSS global uma vez por sessão do browser."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

_CSS_SESSION_FLAG = "sc_css_injected_v1"
_CSS_FILE = Path(__file__).resolve().parent / "assets" / "custom.css"


def inject_styles() -> None:
    if st.session_state.get(_CSS_SESSION_FLAG):
        return
    if _CSS_FILE.is_file():
        css = _CSS_FILE.read_text(encoding="utf-8")
        st.markdown(f"<style>\n{css}\n</style>", unsafe_allow_html=True)
    st.session_state[_CSS_SESSION_FLAG] = True

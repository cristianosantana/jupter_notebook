"""Render de uma mensagem do assistente (markdown + HTML estruturado)."""

from __future__ import annotations

from typing import Any

import streamlit as st

from smartchat.message_processing.html_render import merged_display_to_html
from smartchat.message_processing.merge_display import merge_assistant_display


def render_assistant_message(content: str, content_blocks: dict[str, Any] | None) -> None:
    merged = merge_assistant_display(content, content_blocks)
    html = merged_display_to_html(merged)
    st.markdown(html, unsafe_allow_html=True)

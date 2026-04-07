"""Configuração a partir de variáveis de ambiente."""

from __future__ import annotations

import os

# Base da API FastAPI (Streamlit não usa proxy Vite)
API_BASE_URL: str = os.environ.get("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")

DEMO_USER_ID: str | None = os.environ.get("DEMO_USER_ID") or None

PAGE_TITLE = "SmartChat"
PAGE_ICON = "🤖"

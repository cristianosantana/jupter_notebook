"""Cliente HTTP para a API FastAPI (sem Streamlit)."""

from __future__ import annotations

from typing import Any

import httpx

from smartchat.config import API_BASE_URL, DEMO_USER_ID


class ApiError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def _url(path: str) -> str:
    return f"{API_BASE_URL}{path}"


def post_chat(
    message: str,
    *,
    session_id: str | None = None,
    target_agent: str | None = None,
    user_id: str | None = None,
    trace_run_id: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"message": message}
    uid = user_id or DEMO_USER_ID
    if uid:
        payload["user_id"] = uid
    if session_id:
        payload["session_id"] = session_id
    if target_agent:
        payload["target_agent"] = target_agent
    if trace_run_id:
        payload["trace_run_id"] = trace_run_id

    with httpx.Client(timeout=300.0) as client:
        r = client.post(_url("/api/chat"), json=payload)
    if r.status_code >= 400:
        raise ApiError(r.text or f"HTTP {r.status_code}", r.status_code)
    return r.json()


def list_sessions(*, user_id: str | None = None, limit: int = 50) -> dict[str, Any]:
    uid = user_id or DEMO_USER_ID
    params: dict[str, Any] = {"limit": limit}
    if uid:
        params["user_id"] = uid
    with httpx.Client(timeout=60.0) as client:
        r = client.get(_url("/api/sessions"), params=params)
    if r.status_code >= 400:
        raise ApiError(r.text or f"HTTP {r.status_code}", r.status_code)
    return r.json()


def get_session(session_id: str) -> dict[str, Any]:
    with httpx.Client(timeout=60.0) as client:
        r = client.get(_url(f"/api/sessions/{session_id}"))
    if r.status_code >= 400:
        raise ApiError(r.text or f"HTTP {r.status_code}", r.status_code)
    return r.json()

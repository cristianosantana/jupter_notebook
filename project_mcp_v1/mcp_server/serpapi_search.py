"""
Pesquisa Google via SerpApi (HTTP). Usado pelo servidor MCP como tool opcional.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

import httpx

_logger = logging.getLogger(__name__)

SERPAPI_SEARCH_URL = "https://serpapi.com/search"


def _serpapi_key() -> str:
    return (os.environ.get("SERPAPI_API_KEY") or "").strip()


def serpapi_enabled() -> bool:
    if (os.environ.get("SERPAPI_ENABLED") or "true").strip().lower() in (
        "0",
        "false",
        "no",
        "off",
    ):
        return False
    return bool(_serpapi_key())


async def google_search_serpapi(
    search_query: str,
    *,
    num_results: int = 8,
    max_output_chars: int = 24_000,
) -> str:
    """
    Executa pesquisa Google via SerpApi e devolve JSON resumido para o modelo.

    ``search_query`` é o texto enviado ao Google (frase ou keywords), derivado da
    pergunta do utilizador — não é ``query_id`` nem identificador de análise interna.

    Em falta de chave ou SerpApi desactivado, devolve JSON com error (a tool não
    deve ser registada nesses casos — mantido por segurança).
    """
    key = _serpapi_key()
    if not key:
        return json.dumps(
            {"error": "SERPAPI_API_KEY não configurada", "query": search_query},
            ensure_ascii=False,
        )

    q = (search_query or "").strip()
    if not q:
        return json.dumps({"error": "search_query vazia"}, ensure_ascii=False)

    n = max(1, min(20, int(num_results)))
    params: dict[str, Any] = {
        "engine": "google",
        "q": q,
        "api_key": key,
        "num": n,
    }

    last_err: str | None = None
    for attempt in range(3):
        try:
            timeout = httpx.Timeout(30.0, connect=10.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                r = await client.get(SERPAPI_SEARCH_URL, params=params)
                if r.status_code == 429:
                    last_err = "rate limit 429"
                    await asyncio.sleep(2**attempt)
                    continue
                r.raise_for_status()
                data = r.json()
        except httpx.HTTPStatusError as e:
            last_err = f"HTTP {e.response.status_code}"
            if e.response.status_code >= 500 and attempt < 2:
                await asyncio.sleep(2**attempt)
                continue
            return json.dumps(
                {"error": last_err, "query": q},
                ensure_ascii=False,
            )
        except Exception as e:
            last_err = str(e)
            if attempt < 2:
                await asyncio.sleep(2**attempt)
                continue
            _logger.warning("serpapi search failed: %s", e)
            return json.dumps(
                {"error": last_err or "falha de rede", "query": q},
                ensure_ascii=False,
            )
        else:
            organic = data.get("organic_results") or []
            trimmed: list[dict[str, Any]] = []
            for item in organic[:n]:
                if not isinstance(item, dict):
                    continue
                trimmed.append(
                    {
                        "title": (item.get("title") or "")[:300],
                        "link": (item.get("link") or "")[:500],
                        "snippet": (item.get("snippet") or "")[:800],
                    }
                )
            answer_box = data.get("answer_box")
            ab_out = None
            if isinstance(answer_box, dict):
                ab_out = {
                    "answer": (answer_box.get("answer") or answer_box.get("result") or "")[
                        :2000
                    ],
                    "title": (answer_box.get("title") or "")[:400],
                }
            out = {
                "query": q,
                "answer_box": ab_out,
                "organic_results": trimmed,
                "search_information": data.get("search_information"),
            }
            text = json.dumps(out, ensure_ascii=False)
            if len(text) > max_output_chars:
                text = text[:max_output_chars] + "\n…[truncado]"
            return text

    return json.dumps(
        {"error": last_err or "esgotaram-se tentativas", "query": q},
        ensure_ascii=False,
    )

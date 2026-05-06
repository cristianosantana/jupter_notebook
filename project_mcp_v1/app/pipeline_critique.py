"""
Parsing da resposta do avaliador crítico (JSON) e tipos auxiliares do pipeline pós-especialista.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

_JSON_FENCE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)


@dataclass
class CritiqueVerdict:
    decisao: str  # APROVAR | DEVOLVER
    pontos_a_acrescentar: list[str]
    justificativa_curta: str
    exige_novos_dados: bool
    exige_pesquisa_web: bool
    limitacoes_da_resposta: str
    aspectos_para_outros_agentes: str
    raw_text: str

    @property
    def aprovar(self) -> bool:
        return self.decisao.strip().upper() == "APROVAR"


def _extract_json_object(raw: str) -> dict[str, Any] | None:
    t = (raw or "").strip()
    if not t:
        return None
    m = _JSON_FENCE.search(t)
    if m:
        t = m.group(1).strip()
    try:
        obj = json.loads(t)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        pass
    i = t.find("{")
    j = t.rfind("}")
    if i >= 0 and j > i:
        try:
            obj = json.loads(t[i : j + 1])
            return obj if isinstance(obj, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def parse_critique_response(raw: str) -> CritiqueVerdict:
    """Interpreta saída do LLM avaliador; valores por defeito seguros se o parse falhar."""
    d = _extract_json_object(raw) or {}
    dec = str(d.get("decisao") or "").strip().upper()
    if dec not in ("APROVAR", "DEVOLVER"):
        # Heurística: texto livre com palavras-chave
        up = (raw or "").upper()
        if "DEVOLVER" in up or "REJEITAR" in up:
            dec = "DEVOLVER"
        else:
            dec = "APROVAR"

    pts = d.get("pontos_a_acrescentar")
    if isinstance(pts, list):
        pontos = [str(x).strip() for x in pts if str(x).strip()]
    elif isinstance(pts, str) and pts.strip():
        pontos = [pts.strip()]
    else:
        pontos = []

    def _bool(v: Any) -> bool:
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.strip().lower() in ("true", "1", "yes", "sim")
        return False

    return CritiqueVerdict(
        decisao=dec,
        pontos_a_acrescentar=pontos,
        justificativa_curta=str(d.get("justificativa_curta") or "")[:2000],
        exige_novos_dados=_bool(d.get("exige_novos_dados")),
        exige_pesquisa_web=_bool(d.get("exige_pesquisa_web")),
        limitacoes_da_resposta=str(d.get("limitacoes_da_resposta") or "")[:2000],
        aspectos_para_outros_agentes=str(d.get("aspectos_para_outros_agentes") or "")[
            :2000
        ],
        raw_text=(raw or "")[:8000],
    )


def format_critique_user_message(v: CritiqueVerdict) -> str:
    """Mensagem user interna para nova volta do especialista."""
    lines = [
        "[Avaliador crítico — feedback interno]",
        f"Decisão: {v.decisao}",
    ]
    if v.justificativa_curta:
        lines.append(f"Justificativa: {v.justificativa_curta}")
    if v.pontos_a_acrescentar:
        lines.append("Pontos a incorporar na resposta (usar dados já obtidos nas tools acima; "
                     "só chama tools de novo se for indispensável):")
        for i, p in enumerate(v.pontos_a_acrescentar, 1):
            lines.append(f"  {i}. {p}")
    if v.exige_novos_dados:
        lines.append("**exige_novos_dados: true** — podes voltar a usar tools MCP de analytics "
                      "(ex.: run_analytics_query) se faltar período/query.")
    if v.exige_pesquisa_web:
        lines.append(
            "**exige_pesquisa_web: true** — deves usar google_search_serpapi com "
            "search_query (texto de pesquisa web), nunca query_id, se ainda não tens "
            "resultados de pesquisa no contexto."
        )
    if v.aspectos_para_outros_agentes:
        lines.append(f"Notas: {v.aspectos_para_outros_agentes}")
    lines.append("Reformula a resposta final ao utilizador em português, completa e coerente.")
    return "\n".join(lines)

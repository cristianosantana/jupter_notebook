from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from typing import Any


from orion_mcp_v2.db.mysql.sql_catalog import QUERY_IDS


class BusinessIntent(str, Enum):
    FATURAMENTO = "FATURAMENTO"
    QUALIDADE = "QUALIDADE"
    PERFORMANCE = "PERFORMANCE"
    OPERACIONAL = "OPERACIONAL"
    ESTRATEGICO = "ESTRATEGICO"


@dataclass(frozen=True)
class PlannedTurn:
    intent: BusinessIntent
    skill_id: str
    query_id: str
    params: dict[str, Any]


_RE_FAT = re.compile(
    r"ticket|valor\s*medio|receita|faturamento|top\s+serv|margem|servi[cç]o|combo|cross[- ]?sell",
    re.I,
)
_RE_QUAL = re.compile(r"retrabalho|reaberta|defeito|qualidade|taxa\s+retrabalho", re.I)
_RE_PERF = re.compile(r"vendedor|ranking|meta|performance", re.I)
_RE_ESTR = re.compile(r"planejamento|cenario|estrat", re.I)


def _detect_intent(message: str) -> BusinessIntent:
    t = (message or "").strip()
    if _RE_QUAL.search(t):
        return BusinessIntent.QUALIDADE
    if _RE_PERF.search(t):
        return BusinessIntent.PERFORMANCE
    if _RE_ESTR.search(t):
        return BusinessIntent.ESTRATEGICO
    if _RE_FAT.search(t):
        return BusinessIntent.FATURAMENTO
    return BusinessIntent.OPERACIONAL


def _skill_for_intent(intent: BusinessIntent) -> str:
    return {
        BusinessIntent.FATURAMENTO: "faturamento_analyzer",
        BusinessIntent.QUALIDADE: "qualidade_analyzer",
        BusinessIntent.PERFORMANCE: "performance_analyzer",
        BusinessIntent.OPERACIONAL: "faturamento_analyzer",
        BusinessIntent.ESTRATEGICO: "performance_analyzer",
    }[intent]


def _default_date_range() -> tuple[str, str]:
    today = date.today()
    start = today.replace(day=1)
    return start.isoformat(), today.isoformat()


def _pick_query(intent: BusinessIntent, message: str) -> str:
    t = message.lower()
    allowed = set(QUERY_IDS)

    def pick(qid: str) -> str:
        if qid in allowed:
            return qid
        return next(iter(sorted(allowed)))

    if intent == BusinessIntent.FATURAMENTO:
        if any(
            x in t
            for x in (
                "combo",
                "cross-sell",
                "cross sell",
                "crosssell",
                "pares de serviço",
                "pares de servico",
            )
        ):
            return pick("cross_selling")
        if "ticket" in t or "médio" in t or "medio" in t:
            return pick("ticket_medio_concessionaria_agg")
        if "top" in t or "serviço" in t or "servico" in t:
            return pick("servicos_vendidos_por_concessionaria")
        return pick("faturamento_ticket_concessionaria_periodo")

    if intent == BusinessIntent.QUALIDADE:
        return pick("taxa_retrabalho_servico_produtivo_concessionaria")

    if intent == BusinessIntent.PERFORMANCE:
        if "ano" in t:
            return pick("performance_vendedor_ano")
        return pick("performance_vendedor_mes")

    if intent == BusinessIntent.ESTRATEGICO:
        return pick("volume_os_concessionaria_mom")

    return pick("ticket_medio_concessionaria_agg")


def decide_turn(user_message: str, *, date_from: str | None, date_to: str | None) -> PlannedTurn:
    intent = _detect_intent(user_message)
    skill_id = _skill_for_intent(intent)
    query_id = _pick_query(intent, user_message)
    d0, d1 = date_from, date_to
    if not d0 or not d1:
        d0, d1 = _default_date_range()
    params: dict[str, Any] = {
        "date_from": d0,
        "date_to": d1,
        "limit": 5000,
        "offset": 0,
    }
    return PlannedTurn(intent=intent, skill_id=skill_id, query_id=query_id, params=params)


def retention_cutoff(*, days: int = 30) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)

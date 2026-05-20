"""
Resolve intenção cognitiva por heurística (sem LLM).

Usa :mod:`intent_patterns` e devolve :class:`~orion_mcp_v3.contracts.cognitive_plan.CognitivePlan`.
"""

from __future__ import annotations

import calendar
import re
import unicodedata
from datetime import date, timedelta

from orion_mcp_v3.contracts.cognitive_plan import (
    AttentionProfile,
    CognitivePlan,
    IntentType,
)
from orion_mcp_v3.contracts.query_plan import RetrievalStrategy
from orion_mcp_v3.runtime import intent_patterns as P
from orion_mcp_v3.runtime.attention_policy import AttentionPolicy


def map_attention_profile_to_policy(profile: AttentionProfile) -> AttentionPolicy:
    """Liga :class:`~AttentionProfile` (contrato) a :class:`~AttentionPolicy` (allocator)."""
    return _ATTENTION_TO_POLICY[profile]


_ATTENTION_TO_POLICY: dict[AttentionProfile, AttentionPolicy] = {
    AttentionProfile.ANALYTICAL: AttentionPolicy.ANALYTICAL,
    AttentionProfile.BALANCED: AttentionPolicy.BALANCED,
    AttentionProfile.MEMORY_FOCUSED: AttentionPolicy.MEMORY_FOCUSED,
    AttentionProfile.CONVERSATIONAL: AttentionPolicy.BALANCED,
    AttentionProfile.PLANNING: AttentionPolicy.PLANNING,
    AttentionProfile.HYBRID: AttentionPolicy.HYBRID,
    AttentionProfile.MONITORING: AttentionPolicy.MONITORING,
    AttentionProfile.EXECUTION: AttentionPolicy.EXECUTION,
}


_MONTHS_PT: dict[str, int] = {
    "jan": 1,
    "janeiro": 1,
    "fev": 2,
    "fevereiro": 2,
    "mar": 3,
    "marco": 3,
    "março": 3,
    "abr": 4,
    "abril": 4,
    "abriu": 4,
    "mai": 5,
    "maio": 5,
    "jun": 6,
    "junho": 6,
    "jul": 7,
    "julho": 7,
    "ago": 8,
    "agosto": 8,
    "set": 9,
    "setembro": 9,
    "out": 10,
    "outubro": 10,
    "nov": 11,
    "novembro": 11,
    "dez": 12,
    "dezembro": 12,
}

_MONTH_NAME_RX = (
    r"jan(?:eiro)?|fev(?:ereiro)?|mar(?:[cç]o)?|abr(?:il|iu)?|mai(?:o)?|jun(?:ho)?|jul(?:ho)?|ago(?:sto)?|set(?:embro)?|out(?:ubro)?|nov(?:embro)?|dez(?:embro)?"
)
_MONTH_RANGE_RX = re.compile(
    rf"\b(?:de\s+|entre\s+)?(?P<start>{_MONTH_NAME_RX})\s+"
    rf"(?:a|até|ate|e)\s+"
    rf"(?P<end>{_MONTH_NAME_RX})\s+de\s+(?P<year>20\d{{2}})\b",
    re.IGNORECASE,
)
_SINGLE_MONTH_RX = re.compile(
    rf"\b(?:em|de|no|na)\s+(?P<month>{_MONTH_NAME_RX})\.?\s+(?:de\s+)?(?P<year>(?:20)?\d{{2}})\b",
    re.IGNORECASE,
)
_MONTH_SLASH_RANGE_RX = re.compile(
    rf"\b(?:de\s+|entre\s+)?(?P<start>{_MONTH_NAME_RX})\.?(?:/(?P<start_year>(?:20)?\d{{2}}))?\s+"
    rf"(?:a|até|ate|e)\s+"
    rf"(?P<end>{_MONTH_NAME_RX})\.?/(?P<end_year>(?:20)?\d{{2}})\b",
    re.IGNORECASE,
)
_DAY_MONTH_RANGE_RX = re.compile(
    rf"\b(?:entre\s+|de\s+)?(?P<start_day>\d{{1,2}})\s+"
    rf"(?:a|até|ate|e)\s+(?P<end_day>\d{{1,2}})\s+de\s+"
    rf"(?P<month>{_MONTH_NAME_RX})\s+de\s+(?P<year>(?:20)?\d{{2}})\b",
    re.IGNORECASE,
)
_ISO_RANGE_RX = re.compile(
    r"\b(?P<start>20\d{2}-\d{1,2}-\d{1,2})\s+(?:a|até|ate|e)\s+"
    r"(?P<end>20\d{2}-\d{1,2}-\d{1,2})\b",
    re.IGNORECASE,
)
_BR_DATE_RANGE_RX = re.compile(
    r"\b(?P<start>\d{1,2}[/-]\d{1,2}[/-](?:20)?\d{2})\s+(?:a|até|ate|e)\s+"
    r"(?P<end>\d{1,2}[/-]\d{1,2}[/-](?:20)?\d{2})\b",
    re.IGNORECASE,
)
_ISO_SINGLE_RX = re.compile(r"\b(?P<date>20\d{2}-\d{1,2}-\d{1,2})\b")
_BR_DATE_SINGLE_RX = re.compile(r"\b(?P<date>\d{1,2}[/-]\d{1,2}[/-](?:20)?\d{2})\b")
_QUARTER_RX = re.compile(
    r"\b(?:q(?P<q1>[1-4])|(?P<q2>[1-4])(?:º|o)?\s+trimestre)\s*(?:de\s*)?(?P<year>(?:20)?\d{2})\b",
    re.IGNORECASE,
)
_LAST_DAYS_RX = re.compile(r"\búltimos?\s+(?P<n>\d+)\s*dias?\b", re.IGNORECASE)
_LAST_MONTHS_RX = re.compile(r"\búltimos?\s+(?P<n>\d+)\s*meses?\b", re.IGNORECASE)


def attention_profile_to_policy_key(profile: AttentionProfile) -> str:
    """Valor estável para logging (mesmo slug que :class:`~AttentionPolicy`)."""
    return profile.value


def _strip_accents(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)
    ).lower()


def _month_number(name: str) -> int | None:
    raw = name.strip().lower().rstrip(".")
    return _MONTHS_PT.get(raw) or _MONTHS_PT.get(_strip_accents(raw))


def _full_year(raw: str) -> int:
    n = int(raw)
    return 2000 + n if n < 100 else n


def _month_end(year: int, month: int) -> str:
    return f"{year:04d}-{month:02d}-{calendar.monthrange(year, month)[1]:02d}"


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _parse_iso_date(raw: str) -> date | None:
    parts = raw.split("-")
    if len(parts) != 3:
        return None
    return _safe_date(int(parts[0]), int(parts[1]), int(parts[2]))


def _parse_br_date(raw: str) -> date | None:
    sep = "/" if "/" in raw else "-"
    parts = raw.split(sep)
    if len(parts) != 3:
        return None
    return _safe_date(_full_year(parts[2]), int(parts[1]), int(parts[0]))


def _period(date_from: date, date_to: date, *, grain: str, source: str) -> dict[str, str] | None:
    if date_to < date_from:
        return None
    return {
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "period_grain": grain,
        "period_source": source,
    }


def _explicit_period_hint(blob: str) -> dict[str, str] | None:
    """Extrai intervalos explícitos e relativos comuns em português."""
    lower = blob.lower()

    m = _ISO_RANGE_RX.search(blob)
    if m:
        start = _parse_iso_date(m.group("start"))
        end = _parse_iso_date(m.group("end"))
        if start is not None and end is not None:
            return _period(start, end, grain="day", source="explicit_iso_range")

    m = _BR_DATE_RANGE_RX.search(blob)
    if m:
        start = _parse_br_date(m.group("start"))
        end = _parse_br_date(m.group("end"))
        if start is not None and end is not None:
            return _period(start, end, grain="day", source="explicit_date_range")

    m = _DAY_MONTH_RANGE_RX.search(blob)
    if m:
        month = _month_number(m.group("month"))
        year = _full_year(m.group("year"))
        if month is not None:
            start = _safe_date(year, month, int(m.group("start_day")))
            end = _safe_date(year, month, int(m.group("end_day")))
            if start is not None and end is not None:
                return _period(start, end, grain="day", source="explicit_day_month_range")

    m = _MONTH_SLASH_RANGE_RX.search(blob)
    if m:
        start_month = _month_number(m.group("start"))
        end_month = _month_number(m.group("end"))
        end_year = _full_year(m.group("end_year"))
        start_year = _full_year(m.group("start_year")) if m.group("start_year") else end_year
        if start_month is not None and end_month is not None:
            return _period(
                date(start_year, start_month, 1),
                date(end_year, end_month, calendar.monthrange(end_year, end_month)[1]),
                grain="month",
                source="explicit_month_abbrev_range",
            )

    m = _MONTH_RANGE_RX.search(blob)
    if m:
        start_month = _month_number(m.group("start"))
        end_month = _month_number(m.group("end"))
        year = _full_year(m.group("year"))
        if start_month is not None and end_month is not None:
            if end_month < start_month:
                return None
            return {
                "date_from": f"{year:04d}-{start_month:02d}-01",
                "date_to": _month_end(year, end_month),
                "period_grain": "month",
                "period_source": "explicit_month_range",
            }

    m = _QUARTER_RX.search(blob)
    if m:
        q = int(m.group("q1") or m.group("q2"))
        year = _full_year(m.group("year"))
        start_month = (q - 1) * 3 + 1
        end_month = start_month + 2
        return {
            "date_from": f"{year:04d}-{start_month:02d}-01",
            "date_to": _month_end(year, end_month),
            "period_grain": "quarter",
            "period_source": "explicit_quarter",
        }

    m = _SINGLE_MONTH_RX.search(blob)
    if m:
        month = _month_number(m.group("month"))
        year = _full_year(m.group("year"))
        if month is not None:
            return {
                "date_from": f"{year:04d}-{month:02d}-01",
                "date_to": _month_end(year, month),
                "period_grain": "month",
                "period_source": "explicit_month",
            }

    m = _ISO_SINGLE_RX.search(blob)
    if m:
        d = _parse_iso_date(m.group("date"))
        if d is not None:
            return _period(d, d, grain="day", source="explicit_iso_date")

    m = _BR_DATE_SINGLE_RX.search(blob)
    if m:
        d = _parse_br_date(m.group("date"))
        if d is not None:
            return _period(d, d, grain="day", source="explicit_date")

    today = date.today()
    if re.search(r"\bhoje\b|\btoday\b", lower):
        return _period(today, today, grain="day", source="relative_today")
    if re.search(r"\bontem\b|\byesterday\b", lower):
        d = today - timedelta(days=1)
        return _period(d, d, grain="day", source="relative_yesterday")
    if re.search(r"\bm[eê]s\s+(atual|corrente)\b", lower):
        return _period(
            date(today.year, today.month, 1),
            date(today.year, today.month, calendar.monthrange(today.year, today.month)[1]),
            grain="month",
            source="relative_current_month",
        )
    if re.search(r"\bano\s+(atual|corrente)\b", lower):
        return _period(
            date(today.year, 1, 1),
            date(today.year, 12, 31),
            grain="year",
            source="relative_current_year",
        )
    if re.search(r"\bano\s+passad[oa]\b", lower):
        year = today.year - 1
        return _period(
            date(year, 1, 1),
            date(year, 12, 31),
            grain="year",
            source="relative_last_year",
        )

    m = _LAST_DAYS_RX.search(blob)
    if m:
        n = max(1, int(m.group("n")))
        return _period(
            today - timedelta(days=n - 1),
            today,
            grain="day",
            source="relative_last_days",
        )

    m = _LAST_MONTHS_RX.search(blob)
    if m:
        n = max(1, int(m.group("n")))
        start_month_index = today.year * 12 + today.month - n
        start_year = start_month_index // 12
        start_month = start_month_index % 12 + 1
        return _period(
            date(start_year, start_month, 1),
            today,
            grain="month",
            source="relative_last_months",
        )
    return None


class IntentResolver:
    """Análise lexical mínima; evoluir para IntentResolver com modelo quando existir política."""

    def resolve(
        self,
        user_input: str,
        recent_context: str | None = None,
        policy_request: str | None = None,
    ) -> CognitivePlan:
        text = (user_input or "").strip()
        blob = f"{text}\n{(recent_context or '').strip()}".strip()

        cmp_ = P._any_match(P.COMPARATIVE_PATTERNS, blob)
        tmp = P._any_match(P.TEMPORAL_PATTERNS, blob)
        ana = P._any_match(P.ANALYTICAL_PATTERNS, blob)
        rec = P._any_match(P.RECALL_PATTERNS, blob)
        mon = P._any_match(P.MONITORING_PATTERNS, blob)
        exe = P._any_match(P.EXECUTION_PATTERNS, blob)
        explicit_period = _explicit_period_hint(blob)
        tmp = tmp or explicit_period is not None

        metrics = self._extract_metric_hints(blob)
        entities = self._extract_entity_hints(blob)
        policy_bias = self._policy_analytics_bias(
            blob,
            policy_request=policy_request,
            has_temporal=tmp,
            has_comparison=cmp_,
            has_metrics=bool(metrics),
            has_entities=bool(entities),
        )
        ana = ana or policy_bias

        needs_comparison = cmp_
        needs_temporal_context = tmp
        needs_analytics = ana
        needs_memory = rec
        needs_baseline = cmp_ and ana
        needs_trend_analysis = ana and tmp
        needs_entity_resolution = ana and (
            "cliente" in blob.lower()
            or "customer" in blob.lower()
            or re.search(r"\b(vendedor|vendedores)\b", blob.lower()) is not None
        )

        intent_type = self._infer_intent_type(
            ana=ana,
            rec=rec,
            cmp_=cmp_,
            tmp=tmp,
            mon=mon,
            exe=exe,
        )
        attention_profile = self._infer_attention_profile(intent_type, mon=mon, exe=exe)
        retrieval_strategy = self._infer_retrieval(ana, rec)
        confidence = self._confidence(
            ana=ana,
            rec=rec,
            cmp_=cmp_,
            tmp=tmp,
            mon=mon,
            exe=exe,
        )

        time_scope = self._time_scope_hint(blob, explicit_period=explicit_period) if tmp else None
        hints = {
            "resolver": "heuristic_v1",
            "signals": {
                "comparative": cmp_,
                "temporal": tmp,
                "analytical": ana,
                "policy_analytical_bias": policy_bias,
                "recall": rec,
                "monitoring": mon,
                "execution": exe,
            },
        }
        if explicit_period is not None:
            hints.update(
                {
                    "date_from": explicit_period["date_from"],
                    "date_to": explicit_period["date_to"],
                    "period_grain": explicit_period["period_grain"],
                    "period_source": explicit_period["period_source"],
                    "explicit_period": {
                        "date_from": explicit_period["date_from"],
                        "date_to": explicit_period["date_to"],
                    },
                }
            )

        return CognitivePlan(
            intent_type=intent_type,
            needs_memory=needs_memory,
            needs_analytics=needs_analytics,
            needs_comparison=needs_comparison,
            needs_temporal_context=needs_temporal_context,
            needs_baseline=needs_baseline,
            needs_trend_analysis=needs_trend_analysis,
            needs_entity_resolution=needs_entity_resolution,
            confidence=confidence,
            entities=entities,
            metrics=metrics,
            time_scope=time_scope,
            retrieval_strategy=retrieval_strategy,
            attention_profile=attention_profile,
            hints=hints,
        )

    def _infer_intent_type(
        self,
        *,
        ana: bool,
        rec: bool,
        cmp_: bool,
        tmp: bool,
        mon: bool,
        exe: bool,
    ) -> IntentType:
        if mon:
            return IntentType.MONITORING
        if exe:
            return IntentType.EXECUTION
        if rec and not ana:
            return IntentType.RECALL
        if cmp_ and (ana or tmp):
            return IntentType.COMPARATIVE
        if tmp and not ana and not rec:
            return IntentType.TEMPORAL
        if ana and rec:
            return IntentType.HYBRID
        if ana:
            return IntentType.ANALYTICAL
        if rec:
            return IntentType.CONVERSATIONAL
        return IntentType.CONVERSATIONAL

    def _infer_attention_profile(
        self,
        intent: IntentType,
        *,
        mon: bool,
        exe: bool,
    ) -> AttentionProfile:
        if mon or intent == IntentType.MONITORING:
            return AttentionProfile.MONITORING
        if exe or intent == IntentType.EXECUTION:
            return AttentionProfile.EXECUTION
        if intent == IntentType.ANALYTICAL:
            return AttentionProfile.ANALYTICAL
        if intent == IntentType.RECALL:
            return AttentionProfile.MEMORY_FOCUSED
        if intent in (IntentType.HYBRID, IntentType.COMPARATIVE):
            return AttentionProfile.HYBRID
        return AttentionProfile.CONVERSATIONAL

    def _infer_retrieval(self, ana: bool, rec: bool) -> RetrievalStrategy:
        if ana and rec:
            return RetrievalStrategy.HYBRID
        if ana:
            return RetrievalStrategy.BROKER_FANOUT
        if rec:
            return RetrievalStrategy.KEYWORD
        return RetrievalStrategy.KEYWORD

    def _confidence(
        self,
        *,
        ana: bool,
        rec: bool,
        cmp_: bool,
        tmp: bool,
        mon: bool,
        exe: bool,
    ) -> float:
        score = 0.35
        for flag in (ana, rec, cmp_, tmp, mon, exe):
            if flag:
                score += 0.11
        return min(0.95, round(score, 3))

    def _time_scope_hint(
        self,
        blob: str,
        *,
        explicit_period: dict[str, str] | None = None,
    ) -> str | None:
        if explicit_period is not None:
            return f"{explicit_period['date_from']}/{explicit_period['date_to']}"
        lower = blob.lower()
        if "últimos" in lower or "last" in lower or "past" in lower:
            return "relative_window"
        if "hoje" in lower or "today" in lower:
            return "today"
        if "ontem" in lower or "yesterday" in lower:
            return "yesterday"
        return None

    @staticmethod
    def _policy_analytics_bias(
        blob: str,
        *,
        policy_request: str | None,
        has_temporal: bool,
        has_comparison: bool,
        has_metrics: bool,
        has_entities: bool,
    ) -> bool:
        policy = (policy_request or "").strip().lower()
        if policy != "analytical":
            return False
        lower = blob.lower()
        data_like = (
            has_temporal
            or has_comparison
            or has_metrics
            or has_entities
            or re.search(
                r"\b(maior|menor|top|ranking|total|m[eé]dia|media|por|recebimento|recebido)\b",
                lower,
            )
            is not None
        )
        return bool(data_like)

    def _extract_metric_hints(self, blob: str) -> tuple[str, ...]:
        out: list[str] = []
        lower = blob.lower()
        for label, needle in (
            ("revenue", "faturamento"),
            ("revenue", "faturou"),
            ("revenue", "faturam"),
            ("revenue", "faturado"),
            ("revenue", "faturação"),
            ("revenue", "revenue"),
            ("revenue", "receita"),
            ("revenue", "recebimento"),
            ("revenue", "recebimentos"),
            ("revenue", "recebido"),
            ("revenue", "recebidos"),
            ("ticket", "ticket"),
        ):
            if needle in lower and label not in out:
                out.append(label)
        # Volume / vendedor: «sales» expande para sinónimos usados no match de templates.
        if (
            re.search(r"\bvendas?\b", lower) is not None
            or re.search(r"\b(vendedor|vendedores)\b", lower) is not None
            or "volume de vendas" in lower
        ):
            if "sales" not in out:
                out.append("sales")
        return tuple(out)

    @staticmethod
    def _extract_entity_hints(blob: str) -> tuple[str, ...]:
        lower = blob.lower()
        out: list[str] = []
        if "concessionária" in lower or "concessionaria" in lower:
            out.append("concessionária")
        if re.search(r"\b(vendedor|vendedores)\b", lower) is not None:
            out.append("vendedor")
        if "pagamento" in lower:
            out.append("pagamento")
        return tuple(out)

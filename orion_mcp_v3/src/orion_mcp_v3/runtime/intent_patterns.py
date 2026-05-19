"""
Padrões textuais para detecção heurística de intenção (sem LLM).

Organiza regex por família — o :class:`~IntentResolver` combina os matches.
"""

from __future__ import annotations

import re

# --- Comparativo / continuação ---
COMPARATIVE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bde novo\b", re.IGNORECASE),
    re.compile(r"\bcontinua\b", re.IGNORECASE),
    re.compile(r"\bmelhorou\b", re.IGNORECASE),
    re.compile(r"\bpiorou\b", re.IGNORECASE),
    re.compile(r"\bcompar(a|ar|ado|ação)\b", re.IGNORECASE),
    re.compile(r"\bversus\b|\bvs\.?\b", re.IGNORECASE),
)

# --- Temporal ---
TEMPORAL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bpor\s+mês\b|\bmensal\b|\bcada\s+mês\b", re.IGNORECASE),
    re.compile(
        r"\b(janeiro|fevereiro|março|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro)\b.*\b20\d{2}\b",
        re.IGNORECASE,
    ),
    re.compile(r"últimos?\s+\d+\s*(meses?|months?)", re.IGNORECASE),
    re.compile(r"\búltimos?\s+meses?\b", re.IGNORECASE),
    re.compile(r"\bhoje\b", re.IGNORECASE),
    re.compile(r"\bontem\b", re.IGNORECASE),
    re.compile(r"\b(semana|mês|ano)\s+passad[oa]\b", re.IGNORECASE),
    re.compile(r"\b(last|past)\s+\d+\s+(months?|weeks?|days?)\b", re.IGNORECASE),
    re.compile(r"\bcomparado\b", re.IGNORECASE),
)

# --- Analytics / negócio ---
ANALYTICAL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bticket\s*médio\b|\bavg\s*ticket\b", re.IGNORECASE),
    re.compile(
        r"\bforma(s)?\s+de\s+pagamento\b|\bmeio(s)?\s+de\s+pagamento\b|\btipo\s+de\s+pagamento\b|\bpayment\s+methods?\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bfaturamento\b|\bfaturou\b|\bfaturam\b|\bfaturamos\b|\bfaturado\b|\bfaturação\b|\brevenue\b|\breceita\b",
        re.IGNORECASE,
    ),
    re.compile(r"\btop\s+\d*\s*clientes?\b|\bmaiores?\s+clientes?\b", re.IGNORECASE),
    re.compile(r"\bvendas?\b|\bsales\b", re.IGNORECASE),
    re.compile(r"\bvolume\s+de\s+vendas\b", re.IGNORECASE),
    re.compile(r"\bagrega|\bagregar\b|\bsum\b|\btotal\b", re.IGNORECASE),
    re.compile(r"\branking\b|\btrend\b|\btendência\b", re.IGNORECASE),
)

# --- Memória / recall conversacional ---
RECALL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bo que\s+falamos\b", re.IGNORECASE),
    re.compile(r"\bme\s+explique\b", re.IGNORECASE),
    re.compile(r"\blembra\b|\brecapitula\b", re.IGNORECASE),
    re.compile(r"\bo que\s+disses\b", re.IGNORECASE),
    re.compile(r"\bcontexto\s+da\s+conversa\b", re.IGNORECASE),
)

MONITORING_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\balerta\b|\balarme\b|\bmonitor(ar|ização)?\b", re.IGNORECASE),
    re.compile(r"\bsubiu\b|\bdesceu\b|\banomaly\b", re.IGNORECASE),
)

EXECUTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bexecuta\b|\brun\b|\bdispara\b|\bgera\s+relatório\b", re.IGNORECASE),
    re.compile(r"\bexporta\b|\bdownload\b", re.IGNORECASE),
)


def _any_match(patterns: tuple[re.Pattern[str], ...], text: str) -> bool:
    return any(p.search(text) for p in patterns)

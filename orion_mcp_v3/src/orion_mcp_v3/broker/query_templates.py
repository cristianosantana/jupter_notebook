"""QueryTemplate + QueryTemplateRegistry — queries SQL pré-definidas parametrizadas."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from orion_mcp_v3.contracts.cognitive_plan import CognitivePlan, IntentType


@dataclass(frozen=True, slots=True)
class QueryTemplate:
    slug: str
    sql: str
    parameters: tuple[str, ...]
    default_params: dict[str, Any]
    answers: tuple[str, ...]
    value_key: str
    time_key: str | None
    grain: str = "day"
    label_key: str | None = None


_METRIC_SYNONYMS: dict[str, list[str]] = {
    "revenue": ["faturamento", "receita", "recebido", "valor"],
    "ticket": ["ticket", "ticket médio"],
    "sales": ["vendas", "vendedor", "venda"],
}


class QueryTemplateRegistry:
    def __init__(self) -> None:
        self._templates: dict[str, QueryTemplate] = {}

    def register(self, template: QueryTemplate) -> None:
        self._templates[template.slug] = template

    def get(self, slug: str) -> QueryTemplate | None:
        return self._templates.get(slug)

    @property
    def slugs(self) -> list[str]:
        return list(self._templates)

    def match(
        self,
        cognitive_plan: CognitivePlan,
        query_text: str = "",
    ) -> QueryTemplate | None:
        if cognitive_plan.intent_type == IntentType.CONVERSATIONAL:
            return None

        best: QueryTemplate | None = None
        best_score = 0

        for tpl in self._templates.values():
            score = self._score(tpl, cognitive_plan, query_text=query_text)
            if score > best_score:
                best_score = score
                best = tpl

        return best

    def match_all(
        self,
        cognitive_plan: CognitivePlan,
        query_text: str = "",
    ) -> list[QueryTemplate]:
        if cognitive_plan.intent_type == IntentType.CONVERSATIONAL:
            return []

        scored = [
            (self._score(tpl, cognitive_plan, query_text=query_text), tpl)
            for tpl in self._templates.values()
        ]
        scored.sort(key=lambda x: x[0], reverse=True)
        return [tpl for score, tpl in scored if score > 0]

    def resolve_params(
        self,
        template: QueryTemplate,
        cognitive_plan: CognitivePlan,
        overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {**template.default_params}

        if cognitive_plan.time_scope:
            scope = cognitive_plan.time_scope
            if "/" in scope:
                parts = scope.split("/", 1)
                params["date_from"] = parts[0]
                params["date_to"] = parts[1]
            else:
                params["date_from"] = scope

        if overrides:
            params.update(overrides)

        return {k: params[k] for k in template.parameters if k in params}

    @staticmethod
    def _score(
        template: QueryTemplate,
        cp: CognitivePlan,
        *,
        query_text: str = "",
    ) -> int:
        score = 0
        cp_metrics_lower = tuple(m.lower() for m in cp.metrics)
        cp_entities_lower = tuple(e.lower() for e in cp.entities)

        expanded_metrics: list[str] = []
        for m in cp_metrics_lower:
            expanded_metrics.append(m)
            if m in _METRIC_SYNONYMS:
                expanded_metrics.extend(_METRIC_SYNONYMS[m])

        for answer in template.answers:
            answer_lower = answer.lower()
            for metric in expanded_metrics:
                if metric in answer_lower:
                    score += 3
                    break
            for entity in cp_entities_lower:
                if entity in answer_lower:
                    score += 3

        if query_text:
            qt_lower = query_text.lower()
            for answer in template.answers:
                if answer.lower() in qt_lower:
                    score += 4

        if cp.needs_temporal_context and template.time_key:
            score += 2

        if template.grain == "day" and cp.needs_temporal_context:
            score += 1

        if cp.needs_comparison and template.slug == "performance_concessionaria":
            score += 2

        return score


# ---------------------------------------------------------------------------
# SQL Templates
# ---------------------------------------------------------------------------

_SQL_FATURAMENTO_DIARIO = """\
SELECT
    DATE(cx.data_vencimento) AS data_recebimento,
    COUNT(*) AS total_recebimentos,
    SUM(cx.valor) AS valor_total_recebido,
    AVG(cx.valor) AS ticket_medio,
    SUM(CASE
        WHEN ct.nome LIKE '%%cartao%%' THEN cx.valor
        ELSE 0
    END) AS total_cartao,
    SUM(CASE
        WHEN ct.nome LIKE '%%pix%%' THEN cx.valor
        ELSE 0
    END) AS total_pix
FROM
    caixas cx
        INNER JOIN
    os os ON os.id = cx.os_id
        INNER JOIN
    os_tipos ost ON ost.id = os.os_tipo_id
        INNER JOIN
    caixa_tipos ct ON ct.id = cx.caixa_tipo_id
WHERE
    cx.deleted_at IS NULL AND ost.ativo = 1
    AND cx.data_vencimento >= %s AND cx.data_vencimento < %s
GROUP BY DATE(cx.data_vencimento)
ORDER BY data_recebimento DESC"""

_SQL_CONCESSIONARIA = """\
SELECT
    LOWER(co.nome) AS concessionaria,
    COUNT(DISTINCT cx.os_id) AS total_os,
    COUNT(*) AS total_recebimentos,
    SUM(cx.valor) AS faturamento,
    AVG(cx.valor) AS ticket_medio
FROM
    caixas cx
        INNER JOIN
    os os ON os.id = cx.os_id
        INNER JOIN
    concessionarias co ON co.id = os.concessionaria_id
        INNER JOIN
    os_tipos ost ON ost.id = os.os_tipo_id
WHERE
    cx.deleted_at IS NULL AND ost.ativo = 1
    AND cx.data_vencimento >= %s AND cx.data_vencimento < %s
GROUP BY co.nome
ORDER BY faturamento DESC"""

_SQL_VENDEDOR = """\
SELECT
    LOWER(fu.nome) AS vendedor,
    COUNT(DISTINCT cx.os_id) AS total_vendas,
    SUM(cx.valor) AS valor_total,
    AVG(cx.valor) AS ticket_medio,
    MAX(cx.valor) AS maior_venda
FROM
    caixas cx
        INNER JOIN
    os os ON os.id = cx.os_id
        INNER JOIN
    funcionarios fu ON fu.id = os.vendedor_id
        INNER JOIN
    os_tipos ost ON ost.id = os.os_tipo_id
WHERE
    cx.deleted_at IS NULL AND ost.ativo = 1
    AND cx.data_vencimento >= %s AND cx.data_vencimento < %s
GROUP BY fu.nome
ORDER BY valor_total DESC"""

_SQL_FORMA_PAGAMENTO = """\
SELECT
    LOWER(ct.nome) AS forma_pagamento,
    COUNT(*) AS qtd_recebimentos,
    SUM(cx.valor) AS total_recebido,
    AVG(cx.valor) AS ticket_medio,
    ROUND((SUM(cx.valor) / (SELECT
                    SUM(valor)
                FROM
                    caixas
                WHERE
                    deleted_at IS NULL)) * 100,
            2) AS percentual_total
FROM
    caixas cx
        INNER JOIN
    caixa_tipos ct ON ct.id = cx.caixa_tipo_id
        INNER JOIN
    os os ON os.id = cx.os_id
        INNER JOIN
    os_tipos ost ON ost.id = os.os_tipo_id
WHERE
    cx.deleted_at IS NULL AND ost.ativo = 1
    AND cx.data_vencimento >= %s AND cx.data_vencimento < %s
GROUP BY ct.nome
ORDER BY total_recebido DESC"""

_SQL_EXECUTIVA = """\
SELECT
    DATE(cx.data_vencimento) AS data_recebimento,
    LOWER(co.nome) AS concessionaria,
    LOWER(de.nome) AS departamento,
    LOWER(fu.nome) AS vendedor,
    LOWER(ct.nome) AS forma_pagamento,
    COUNT(*) AS qtd_recebimentos,
    COUNT(DISTINCT cx.os_id) AS qtd_os,
    SUM(cx.valor) AS valor_total,
    AVG(cx.valor) AS ticket_medio
FROM
    caixas cx
        INNER JOIN
    os os ON os.id = cx.os_id
        INNER JOIN
    departamentos de ON de.id = os.departamento_id
        INNER JOIN
    funcionarios fu ON fu.id = os.vendedor_id
        INNER JOIN
    concessionarias co ON co.id = os.concessionaria_id
        INNER JOIN
    caixa_tipos ct ON ct.id = cx.caixa_tipo_id
        INNER JOIN
    os_tipos ost ON ost.id = os.os_tipo_id
WHERE
    cx.deleted_at IS NULL AND ost.ativo = 1
    AND cx.data_vencimento >= %s AND cx.data_vencimento < %s
GROUP BY DATE(cx.data_vencimento), co.nome, de.nome, fu.nome, ct.nome
ORDER BY data_recebimento DESC"""


_DEFAULT_DATE_PARAMS: dict[str, Any] = {
    "date_from": "1900-01-01",
    "date_to": "2099-12-31",
}


def _build_registry() -> QueryTemplateRegistry:
    reg = QueryTemplateRegistry()

    reg.register(QueryTemplate(
        slug="faturamento_diario",
        sql=_SQL_FATURAMENTO_DIARIO,
        parameters=("date_from", "date_to"),
        default_params={**_DEFAULT_DATE_PARAMS},
        answers=(
            "faturamento diário",
            "receita por dia",
            "recebimentos por data",
            "quanto foi recebido por dia",
            "evolução diária de receita",
            "total cartão e pix por dia",
            "ticket médio diário",
            "revenue",
            "daily revenue",
            "ticket",
        ),
        value_key="valor_total_recebido",
        time_key="data_recebimento",
        grain="day",
    ))

    reg.register(QueryTemplate(
        slug="performance_concessionaria",
        sql=_SQL_CONCESSIONARIA,
        parameters=("date_from", "date_to"),
        default_params={**_DEFAULT_DATE_PARAMS},
        answers=(
            "faturamento por concessionária",
            "performance de concessionária",
            "receita por concessionária",
            "ranking de concessionárias",
            "comparação entre concessionárias",
            "qual concessionária fatura mais",
            "revenue",
            "sales",
        ),
        value_key="faturamento",
        time_key=None,
        grain="total",
        label_key="concessionaria",
    ))

    reg.register(QueryTemplate(
        slug="performance_vendedor",
        sql=_SQL_VENDEDOR,
        parameters=("date_from", "date_to"),
        default_params={**_DEFAULT_DATE_PARAMS},
        answers=(
            "faturamento por vendedor",
            "performance de vendedor",
            "ranking de vendedores",
            "qual vendedor vendeu mais",
            "ticket médio por vendedor",
            "vendas por vendedor",
            "revenue",
            "sales",
            "ticket",
        ),
        value_key="valor_total",
        time_key=None,
        grain="total",
        label_key="vendedor",
    ))

    reg.register(QueryTemplate(
        slug="formas_pagamento",
        sql=_SQL_FORMA_PAGAMENTO,
        parameters=("date_from", "date_to"),
        default_params={**_DEFAULT_DATE_PARAMS},
        answers=(
            "formas de pagamento",
            "forma de pagamento",
            "distribuição por forma de pagamento",
            "percentual por forma de pagamento",
            "quanto foi pago em pix",
            "quanto foi pago em cartão",
            "receita por tipo de pagamento",
            "revenue",
            "sales",
        ),
        value_key="total_recebido",
        time_key=None,
        grain="total",
        label_key="forma_pagamento",
    ))

    reg.register(QueryTemplate(
        slug="visao_executiva",
        sql=_SQL_EXECUTIVA,
        parameters=("date_from", "date_to"),
        default_params={**_DEFAULT_DATE_PARAMS},
        answers=(
            "visão executiva",
            "relatório completo",
            "power bi",
            "dados completos de faturamento",
            "faturamento por concessionária vendedor e data",
            "dashboard executivo",
            "revenue",
            "sales",
        ),
        value_key="valor_total",
        time_key="data_recebimento",
        grain="day",
    ))

    return reg


ANALYTICS_TEMPLATES = _build_registry()

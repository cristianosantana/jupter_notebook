"""QueryTemplate + QueryTemplateRegistry — queries SQL pré-definidas parametrizadas."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from orion_mcp_v3.broker.queries import get_all_modules
from orion_mcp_v3.contracts.cognitive_plan import CognitivePlan, IntentType

DEFAULT_LOOKBACK_DAYS = 30


def _default_date_from() -> str:
    return (date.today() - timedelta(days=DEFAULT_LOOKBACK_DAYS)).isoformat()


def _default_date_to() -> str:
    return (date.today() + timedelta(days=1)).isoformat()


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
        params: dict[str, Any] = {}
        for k, v in template.default_params.items():
            params[k] = v() if callable(v) else v

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
            # Perguntas por concessionária: ``faturamento_diário`` agrega por dia global (sem dimensão
            # loja); preferir séries mensais (``visao_executiva``) ou ranking no período.
            if "concessionária" in qt_lower or "concessionaria" in qt_lower:
                if template.slug == "visao_executiva":
                    score += 10
                elif template.slug == "performance_concessionaria":
                    score += 8
                elif template.slug == "faturamento_diario":
                    score -= 8

            # Perguntas sobre dimensão vendedor (sem pedir concessionária) → ranking por vendedor.
            has_vendedor_dim = re.search(r"\b(vendedor|vendedores)\b", qt_lower) is not None
            has_concessionaria_dim = (
                "concessionária" in qt_lower or "concessionaria" in qt_lower
            )
            # Série temporal por loja (mês) vs. totais no período — com contexto temporal explícito,
            # preferir granularidade mensal ``visao_executiva``.
            if (
                has_concessionaria_dim
                and cp.needs_temporal_context
                and template.slug == "visao_executiva"
            ):
                score += 22
            if has_vendedor_dim and not has_concessionaria_dim:
                if template.slug == "performance_vendedor":
                    score += 14
                elif template.slug in ("visao_executiva", "faturamento_diario"):
                    score -= 6

        if cp.needs_temporal_context and template.time_key:
            score += 2

        if template.grain == "day" and cp.needs_temporal_context:
            score += 1

        if cp.needs_comparison and template.slug == "performance_concessionaria":
            score += 2

        return score


# ---------------------------------------------------------------------------
# Registry builder — importa SQL dos módulos em broker/queries/
# ---------------------------------------------------------------------------

def _default_params() -> dict[str, Any]:
    return {"date_from": _default_date_from, "date_to": _default_date_to}


def _build_registry() -> QueryTemplateRegistry:
    reg = QueryTemplateRegistry()

    for slug, mod in get_all_modules().items():
        params_tuple = ("date_from", "date_to")
        if hasattr(mod, "PARAMETERS"):
            params_tuple = mod.PARAMETERS

        reg.register(QueryTemplate(
            slug=slug,
            sql=mod.SQL,
            parameters=params_tuple,
            default_params=_default_params(),
            answers=mod.ANSWERS,
            value_key=mod.VALUE_KEY,
            time_key=getattr(mod, "TIME_KEY", None),
            grain=getattr(mod, "GRAIN", "day"),
            label_key=getattr(mod, "LABEL_KEY", None),
        ))

    return reg


ANALYTICS_TEMPLATES = _build_registry()

"""
Fan-out heurístico: :class:`~CognitivePlan` → vários :class:`~SemanticQueryPlan` (sem LLM).

Gating por ``confidence``, ângulos complementares (período anterior, métricas, baseline),
dedupe por assinatura SQL pós-:func:`~merge_executable_hints` e teto de 4 planos.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
import re
from typing import Any

from orion_mcp_v3.broker.planner import build_query_plan
from orion_mcp_v3.broker.query_collections import ANALYTICS_COLLECTIONS, QueryCollectionCatalog
from orion_mcp_v3.broker.query_templates import QueryTemplateRegistry
from orion_mcp_v3.broker.semantic_query_compiler import merge_executable_hints
from orion_mcp_v3.broker.sql_compiler import SqlAllowlist, SqlCompilationError, compile_select
from orion_mcp_v3.contracts.cognitive_plan import CognitivePlan
from orion_mcp_v3.contracts.query_plan import RetrievalStrategy, SemanticQueryPlan


def _os_execution_shell(
    *,
    sql_filters: tuple[dict[str, Any], ...],
    sql_columns: tuple[dict[str, Any], ...],
    sql_order_by: dict[str, Any],
    limit: int = 1000,
) -> dict[str, Any]:
    """Hints executáveis OS+joins (evita que :func:`merge_executable_hints` sobrescreva com o default 2026)."""
    return {
        "sql_table": "os",
        "sql_joins": (
            {
                "join_table": "clientes",
                "alias": "cli",
                "on_left_column": "cliente_id",
                "on_right_column": "id",
            },
            {
                "join_table": "os_servicos",
                "alias": "svc",
                "on_left_column": "id",
                "on_right_column": "os_id",
            },
        ),
        "sql_columns": sql_columns,
        "sql_group_by": ({"qualifier": "os", "column": "cliente_id"},),
        "sql_filters": sql_filters,
        "sql_order_by": sql_order_by,
        "sql_omit_limit": False,
        "limit": limit,
    }


def _merge_plan_hints(base: SemanticQueryPlan, execution: Mapping[str, Any]) -> SemanticQueryPlan:
    merged = {**dict(base.hints), **dict(execution)}
    return replace(base, hints=merged)


def _plan_signature(
    plan: SemanticQueryPlan,
    allowlist: SqlAllowlist,
    *,
    default_limit: int,
    default_sql_table: str,
) -> tuple[str, tuple[Any, ...]]:
    merged = merge_executable_hints(
        plan,
        allowlist,
        None,
        default_limit=default_limit,
        default_sql_table=default_sql_table,
    )
    compiled = compile_select(merged, allowlist, default_limit=default_limit)
    return (compiled.sql, compiled.params)


def dedupe_plans(
    plans: list[SemanticQueryPlan],
    allowlist: SqlAllowlist,
    *,
    default_limit: int = 1000,
    default_sql_table: str = "os",
) -> list[SemanticQueryPlan]:
    """Remove planos que compilam para o mesmo SQL+params (pós-merge de hints executáveis)."""
    seen: set[tuple[str, tuple[Any, ...]]] = set()
    out: list[SemanticQueryPlan] = []
    for p in plans:
        try:
            sig = _plan_signature(p, allowlist, default_limit=default_limit, default_sql_table=default_sql_table)
        except (SqlCompilationError, ValueError):
            sig = (p.intent_slug, (repr(sorted(p.hints.items())),))
        if sig in seen:
            continue
        seen.add(sig)
        out.append(p)
    return out


class QueryExpander:
    """
    Expande um :class:`CognitivePlan` em N :class:`SemanticQueryPlan` determinísticos.

    - ``confidence > 0.8``: só ``primary``
    - ``0.5 <= confidence <= 0.8``: ``primary`` + 1 ângulo complementar (por prioridade)
    - ``confidence < 0.5``: ``primary`` + até 2 ângulos complementares

    Prioridade dos extras: ``prior_period`` (comparação/temporal) → ``metric.*`` (várias métricas)
    → ``baseline``.
    """

    def __init__(
        self,
        *,
        default_limit: int = 1000,
        default_sql_table: str = "os",
        max_plans: int = 4,
        registry: QueryTemplateRegistry | None = None,
        collections: QueryCollectionCatalog = ANALYTICS_COLLECTIONS,
    ) -> None:
        self._default_limit = default_limit
        self._default_sql_table = default_sql_table
        self._max_plans = max_plans
        self._registry = registry
        self._collections = collections

    def expand(
        self,
        cognitive: CognitivePlan,
        allowlist: SqlAllowlist,
        *,
        query_text: str | None = None,
        correlation_id: str | None = None,
    ) -> list[SemanticQueryPlan]:
        template_plans = self._try_template_plans(
            cognitive,
            query_text=query_text or "",
            correlation_id=correlation_id,
        )
        if template_plans:
            if any(p.hints.get("collection_slug") for p in template_plans):
                return template_plans
            return template_plans[: self._max_plans]

        primary = build_query_plan(
            cognitive,
            query_text=query_text,
            intent_slug="primary",
            correlation_id=correlation_id,
        )
        plans: list[SemanticQueryPlan] = [primary]

        c = float(cognitive.confidence)
        if c > 0.8:
            return dedupe_plans(
                plans,
                allowlist,
                default_limit=self._default_limit,
                default_sql_table=self._default_sql_table,
            )[: self._max_plans]

        max_extra = 1 if c >= 0.5 else 2
        extras = self._candidate_extras(cognitive, query_text=query_text, correlation_id=correlation_id)
        for extra in extras[:max_extra]:
            plans.append(extra)

        deduped = dedupe_plans(
            plans,
            allowlist,
            default_limit=self._default_limit,
            default_sql_table=self._default_sql_table,
        )
        return deduped[: self._max_plans]

    def _try_template_plans(
        self,
        cognitive: CognitivePlan,
        *,
        query_text: str = "",
        correlation_id: str | None,
    ) -> list[SemanticQueryPlan]:
        if self._registry is None:
            return []

        preferred_collection_slug = _preferred_collection_slug(cognitive)
        preferred_collection = self._collections.get(preferred_collection_slug) if preferred_collection_slug else None
        matched_collections = (preferred_collection,) if preferred_collection is not None else self._collections.match_all(query_text, cognitive)
        if matched_collections:
            collection = matched_collections[0]
            plans: list[SemanticQueryPlan] = []
            for slug in collection.matched_template_slugs(query_text):
                tpl = self._registry.get(slug)
                if tpl is None:
                    continue
                plan = self._template_plan(
                    tpl,
                    cognitive,
                    correlation_id=correlation_id,
                    semantic_reason="collection_fanout",
                )
                plans.append(
                    replace(
                        plan,
                        hints={
                            **dict(plan.hints),
                            "collection_slug": collection.slug,
                            "collection_reason": "collection_catalog_match",
                            "collection_presentation_mode": collection.presentation_mode,
                            "selected_metric": _collection_default_measure(tpl, plan.hints.get("selected_metric")),
                            "selected_dimension": _collection_default_dimension(tpl, plan.hints.get("selected_dimension")),
                            "selected_operation": plan.hints.get("selected_operation") or collection.default_operation,
                        },
                    )
                )
            if plans:
                return plans

        preferred_slug = _preferred_template_slug(cognitive)
        if preferred_slug:
            tpl = self._registry.get(preferred_slug)
            if tpl is not None:
                semantic_reason = _hint_value(cognitive, "semantic_reason") or "validated_intent_contract"
                return [
                    self._template_plan(
                        tpl,
                        cognitive,
                        correlation_id=correlation_id,
                        semantic_reason=semantic_reason,
                    )
                ]

        matched = self._registry.match_all(cognitive, query_text=query_text)
        if not matched:
            return []

        return [
            self._template_plan(
                tpl,
                cognitive,
                correlation_id=correlation_id,
                semantic_reason="registry_match",
            )
            for tpl in matched
        ]

    def _template_plan(
        self,
        tpl: Any,
        cognitive: CognitivePlan,
        *,
        correlation_id: str | None,
        semantic_reason: str,
    ) -> SemanticQueryPlan:
        params = self._registry.resolve_params(tpl, cognitive) if self._registry is not None else {}
        contract = cognitive.hints.get("intent_contract") if isinstance(cognitive.hints, Mapping) else None
        contract_dict = contract if isinstance(contract, Mapping) else {}
        entity_filters = _hint_object(cognitive, "entity_filters") or contract_dict.get("entity_filters") or ()
        return SemanticQueryPlan(
            intent_slug=f"template.{tpl.slug}",
            strategy=RetrievalStrategy.BROKER_FANOUT,
            hints={
                "_template": tpl,
                "template_slug": tpl.slug,
                "template_params": params,
                "selected_metric": _hint_value(cognitive, "selected_metric") or contract_dict.get("metric") or _first(cognitive.metrics),
                "selected_dimension": _hint_value(cognitive, "selected_dimension")
                or contract_dict.get("dimension")
                or _first(cognitive.entities),
                "selected_operation": _hint_value(cognitive, "selected_operation") or contract_dict.get("operation"),
                "entity_filters": _normalize_entity_filters(entity_filters),
                "result_scope": _hint_object(cognitive, "result_scope") or contract_dict.get("result_scope"),
                "sort": _hint_object(cognitive, "sort") or contract_dict.get("sort"),
                "semantic_reason": semantic_reason,
            },
            correlation_id=correlation_id,
        )

    def _candidate_extras(
        self,
        cognitive: CognitivePlan,
        *,
        query_text: str | None,
        correlation_id: str | None,
    ) -> list[SemanticQueryPlan]:
        ordered: list[SemanticQueryPlan] = []

        if cognitive.needs_comparison or cognitive.needs_temporal_context:
            base = build_query_plan(
                cognitive,
                query_text=query_text,
                intent_slug="prior_period",
                correlation_id=correlation_id,
            )
            prior_filters = (
                {"qualifier": "os", "column": "paga", "op": "=", "value": 1},
                {"qualifier": "os", "column": "created_at", "op": ">=", "value": "2024-01-01"},
                {"qualifier": "os", "column": "created_at", "op": "<", "value": "2026-01-01"},
            )
            shell = _os_execution_shell(
                sql_filters=prior_filters,
                sql_columns=(
                    {"qualifier": "os", "column": "cliente_id"},
                    {
                        "agg": "SUM",
                        "qualifier": "svc",
                        "column": "valor_venda_real",
                        "alias": "total_faturamento",
                    },
                ),
                sql_order_by={"direction": "desc", "alias": "total_faturamento"},
                limit=self._default_limit,
            )
            shell["fanout_angle"] = "prior_period"
            ordered.append(_merge_plan_hints(base, shell))

        # Métricas adicionais (evita duplicar o eixo principal = ``metrics[0]``).
        if len(cognitive.metrics) > 1:
            for m in cognitive.metrics[1:3]:
                slug = f"metric.{m}"
                cog_m = replace(cognitive, metrics=(m,))
                base = build_query_plan(
                    cog_m,
                    query_text=query_text,
                    intent_slug=slug,
                    correlation_id=correlation_id,
                )
                if m == "ticket":
                    cols = (
                        {"qualifier": "os", "column": "cliente_id"},
                        {
                            "agg": "COUNT",
                            "qualifier": "svc",
                            "column": "servico_id",
                            "alias": "ticket_count",
                        },
                    )
                    order = {"direction": "desc", "alias": "ticket_count"}
                    vfilters = (
                        {"qualifier": "os", "column": "paga", "op": "=", "value": 1},
                        {"qualifier": "os", "column": "created_at", "op": ">=", "value": "2026-01-01"},
                    )
                else:
                    cols = (
                        {"qualifier": "os", "column": "cliente_id"},
                        {
                            "agg": "SUM",
                            "qualifier": "svc",
                            "column": "valor_venda_real",
                            "alias": "total_faturamento",
                        },
                    )
                    order = {"direction": "desc", "alias": "total_faturamento"}
                    vfilters = (
                        {"qualifier": "os", "column": "paga", "op": "=", "value": 1},
                        {"qualifier": "os", "column": "created_at", "op": ">=", "value": "2026-01-01"},
                    )
                shell = _os_execution_shell(
                    sql_filters=vfilters,
                    sql_columns=cols,
                    sql_order_by=order,
                    limit=self._default_limit,
                )
                shell["fanout_angle"] = slug
                ordered.append(_merge_plan_hints(base, shell))

        if cognitive.needs_baseline:
            base = build_query_plan(
                cognitive,
                query_text=query_text,
                intent_slug="baseline",
                correlation_id=correlation_id,
            )
            baseline_filters = (
                {"qualifier": "os", "column": "paga", "op": "=", "value": 1},
                {"qualifier": "os", "column": "created_at", "op": ">=", "value": "2020-01-01"},
            )
            cols = (
                {"qualifier": "os", "column": "cliente_id"},
                {
                    "agg": "AVG",
                    "qualifier": "svc",
                    "column": "valor_venda_real",
                    "alias": "avg_faturamento",
                },
            )
            shell = _os_execution_shell(
                sql_filters=baseline_filters,
                sql_columns=cols,
                sql_order_by={"direction": "desc", "alias": "avg_faturamento"},
                limit=self._default_limit,
            )
            shell["fanout_angle"] = "baseline"
            ordered.append(_merge_plan_hints(base, shell))

        return ordered


def _preferred_template_slug(cognitive: CognitivePlan) -> str | None:
    hints = cognitive.hints if isinstance(cognitive.hints, Mapping) else {}
    raw = hints.get("template_slug")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    contract = hints.get("intent_contract")
    if isinstance(contract, Mapping):
        raw = contract.get("template_slug")
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return None


def _preferred_collection_slug(cognitive: CognitivePlan) -> str | None:
    hints = cognitive.hints if isinstance(cognitive.hints, Mapping) else {}
    raw = hints.get("collection_slug")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    contract = hints.get("intent_contract")
    if isinstance(contract, Mapping):
        raw = contract.get("collection_slug")
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return None


def _hint_value(cognitive: CognitivePlan, key: str) -> str | None:
    hints = cognitive.hints if isinstance(cognitive.hints, Mapping) else {}
    raw = hints.get(key)
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return None


def _hint_object(cognitive: CognitivePlan, key: str) -> Any:
    hints = cognitive.hints if isinstance(cognitive.hints, Mapping) else {}
    return hints.get(key)


def _normalize_entity_filters(raw: Any) -> tuple[dict[str, str], ...]:
    if not isinstance(raw, (list, tuple)):
        return ()
    out: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        dimension = str(item.get("dimension") or "").strip()
        value = str(item.get("value") or "").strip()
        if not dimension or not value:
            continue
        if dimension in _TEMPORAL_FILTER_DIMENSIONS:
            continue
        match = _normalize_filter_match(
            dimension=dimension,
            value=value,
            match=str(item.get("match") or "contains"),
        )
        out.append({"dimension": dimension, "value": value, "match": match})
    return tuple(out)


def _normalize_filter_match(*, dimension: str, value: str, match: str) -> str:
    normalized = match.strip().lower()
    if normalized not in {"contains", "exact"}:
        normalized = "contains"
    if normalized != "exact":
        return normalized
    if dimension in {"periodo", "data_pagamento"} and re.fullmatch(r"20\d{2}(?:-\d{2})?(?:-\d{2})?", value):
        return "exact"
    return "contains"


_TEMPORAL_FILTER_DIMENSIONS = frozenset({"periodo", "data_pagamento"})


def _first(values: tuple[str, ...]) -> str | None:
    return values[0] if values else None


def _collection_default_dimension(tpl: Any, fallback: Any) -> Any:
    capability = getattr(tpl, "capability", None)
    default_dimension = getattr(capability, "default_dimension", None)
    return default_dimension or fallback


def _collection_default_measure(tpl: Any, fallback: Any) -> Any:
    capability = getattr(tpl, "capability", None)
    default_measure = getattr(capability, "default_measure", None)
    return default_measure or fallback

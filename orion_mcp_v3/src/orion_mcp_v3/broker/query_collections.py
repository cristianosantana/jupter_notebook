"""Catalogo declarativo de colecoes analiticas compostas por QueryTemplates."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from orion_mcp_v3.broker.query_templates import QueryTemplateRegistry
    from orion_mcp_v3.contracts.cognitive_plan import CognitivePlan


def _norm(text: str) -> str:
    raw = "".join(
        c for c in unicodedata.normalize("NFKD", text.lower()) if not unicodedata.combining(c)
    )
    return re.sub(r"\s+", " ", raw).strip()


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(_norm(term) in text for term in terms if term.strip())


@dataclass(frozen=True, slots=True)
class QueryCollectionItem:
    template_slug: str
    match_terms: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class QueryCollection:
    slug: str
    descriptions: tuple[str, ...]
    items: tuple[QueryCollectionItem, ...]
    default_operation: str = "list"
    presentation_mode: str = "sections"

    @property
    def template_slugs(self) -> tuple[str, ...]:
        return tuple(item.template_slug for item in self.items)

    def matched_template_slugs(self, query_text: str) -> tuple[str, ...]:
        text = _norm(query_text)
        matched = tuple(
            item.template_slug
            for item in self.items
            if item.match_terms and _contains_any(text, item.match_terms)
        )
        return matched or self.template_slugs

    def matches(self, query_text: str) -> bool:
        return _contains_any(_norm(query_text), self.descriptions)


class QueryCollectionCatalog:
    def __init__(self, collections: tuple[QueryCollection, ...]) -> None:
        self._collections = {collection.slug: collection for collection in collections}

    def get(self, slug: str) -> QueryCollection | None:
        return self._collections.get(slug)

    def match_all(
        self,
        query_text: str,
        cognitive_plan: "CognitivePlan | None" = None,
    ) -> tuple[QueryCollection, ...]:
        del cognitive_plan
        return tuple(
            collection
            for collection in self._collections.values()
            if collection.matches(query_text)
        )

    def validate_templates(self, registry: "QueryTemplateRegistry") -> tuple[str, ...]:
        missing: list[str] = []
        for collection in self._collections.values():
            for slug in collection.template_slugs:
                if registry.get(slug) is None:
                    missing.append(slug)
        return tuple(missing)


FECHAMENTO_GERENCIAL_TEMPLATES: tuple[str, ...] = (
    "fechamento_faturamento_comissao_concessionaria_periodo",
    "fechamento_faturamento_comissao_tipo_os_concessionaria_periodo",
    "fechamento_producao_servico",
    "fechamento_producao_produto",
    "fechamento_faturamento_tipo_pagamento",
    "fechamento_faturamento_tipo_venda",
    "fechamento_faturamento_tipo_venda_produtos",
    "fechamento_parcelamento_cartao",
    "fechamento_taxas_cartao_credito",
)


ANALYTICS_COLLECTIONS = QueryCollectionCatalog(
    (
        QueryCollection(
            slug="fechamento_gerencial_por_mes",
            descriptions=(
                "fechamento gerencial",
                "fechamento mensal completo",
                "resumo gerencial mensal",
            ),
            items=(
                QueryCollectionItem(
                    "fechamento_faturamento_comissao_concessionaria_periodo",
                    ("comissao", "concessionaria"),
                ),
                QueryCollectionItem(
                    "fechamento_faturamento_comissao_tipo_os_concessionaria_periodo",
                    ("comissao", "concessionaria", "tipo de os"),
                ),
                QueryCollectionItem(
                    "fechamento_producao_servico",
                    ("producao por servico", "produzido por servico", "servicos produzidos"),
                ),
                QueryCollectionItem(
                    "fechamento_producao_produto",
                    ("producao por produto", "produzido por produto", "produtos produzidos"),
                ),
                QueryCollectionItem(
                    "fechamento_faturamento_tipo_pagamento",
                    ("tipo de pagamento", "forma de pagamento", "total liquido"),
                ),
                QueryCollectionItem(
                    "fechamento_faturamento_tipo_venda",
                    ("tipo de venda", "tipo de os"),
                ),
                QueryCollectionItem(
                    "fechamento_faturamento_tipo_venda_produtos",
                    ("tipo de venda", "tipo de os", "produtos"),
                ),
                QueryCollectionItem(
                    "fechamento_parcelamento_cartao",
                    ("parcela", "parcelamento", "quantidade de parcelas"),
                ),
                QueryCollectionItem(
                    "fechamento_taxas_cartao_credito",
                    ("taxa de cartao", "taxas de cartao", "bandeira", "valor bruto", "valor liquido"),
                ),
            ),
            default_operation="list",
            presentation_mode="sections",
        ),
    )
)

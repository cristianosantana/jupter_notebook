"""Testes unitários de eixos de escopo schema-aware."""

from __future__ import annotations

from orion_mcp_v3.public_chat.domain.key_metrics_introspection import (
    KeyMetricsIndexEntry,
    partition_scope_entities,
    scope_axes_for_entry,
)


def _entry(
    *,
    key: str,
    dimension: str,
    entity_field: str,
    subdimension: str | None = None,
) -> KeyMetricsIndexEntry:
    return KeyMetricsIndexEntry(
        key=key,
        dimension=dimension,
        metric_kind="revenue",
        entity_field=entity_field,
        value_field="valor",
        schema="ranked_list",
        sample_labels=(),
        shape="array",
        subdimension=subdimension,
    )


def test_scope_axes_parcelamento_de_cartao():
    entry = _entry(
        key="parcelamento_de_cartao",
        dimension="parcelas",
        entity_field="parcelas",
    )
    assert scope_axes_for_entry(entry) == frozenset({"parcelas"})


def test_scope_axes_comissao_matrix_two_axes():
    entry = _entry(
        key="comissao_por_tipo_de_os_por_concessionaria",
        dimension="tipo_os",
        entity_field="tipo_os",
        subdimension="concessionaria",
    )
    assert scope_axes_for_entry(entry) == frozenset({"tipo_os", "concessionaria"})


def test_scope_axes_faturamento_e_comissao_por_concessionaria():
    entry = _entry(
        key="faturamento_e_comissao_por_concessionaria",
        dimension="concessionaria",
        entity_field="concessionaria",
    )
    assert scope_axes_for_entry(entry) == frozenset({"concessionaria"})


def test_partition_scope_entities_discards_forma_pagamento_for_parcelamento():
    entry = _entry(
        key="parcelamento_de_cartao",
        dimension="parcelas",
        entity_field="parcelas",
    )
    axes = scope_axes_for_entry(entry)
    applicable, discarded = partition_scope_entities(
        (
            ("forma_pagamento", "cartao_de_credito"),
            ("parcelas", "1X"),
        ),
        axes,
        exclude_dimensions=("parcelas",),
    )
    assert applicable == ()
    assert len(discarded) == 2
    reasons = {item["reason"] for item in discarded}
    assert reasons == {"not_in_schema", "excluded_loop_dim"}

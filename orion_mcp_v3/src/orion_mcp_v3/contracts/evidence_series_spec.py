"""
Contrato: liga um resultado analítico (:class:`~AnalyticsResult`) às chaves de série
usadas por :class:`~EvidenceBuilder` (valor temporal, granularidade, identificador).

Um fan-out com vários templates SQL distintos deve ter **uma especificação por
resultado**, para não aplicar a métrica do primeiro plano a todas as linhas.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EvidenceSeriesSpec:
    """
    Parâmetros de uma série numérica extraída de ``rows`` para construir evidência.

    ``template_slug`` é preenchido quando a origem é um :class:`~QueryTemplate`
    registado; caso contrário permanece ``None`` (ex.: plano compilado a partir
    de hints SQL).
    """

    value_key: str
    value_kind: str = "money"
    time_key: str | None = None
    grain: str = "month"
    id_key: str | None = "id"
    label_key: str | None = None
    template_slug: str | None = None
    intent_slug: str | None = None

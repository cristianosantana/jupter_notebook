"""Contrato produtor/consumidor para índices ``key_metrics``."""

from __future__ import annotations

import logging
import re
from typing import Any, Mapping

logger = logging.getLogger(__name__)

METRIC_KINDS = frozenset({"revenue", "commission", "share", "count", "rate"})
SCHEMA_RANKED_LIST = "ranked_list"
SCHEMA_TABLE = "table"
SCHEMA_SCALAR = "scalar"
_HEAD_TAIL_LIMIT = 10
_HEAD_TAIL_FULL_THRESHOLD = 20

CANONICAL_INDEX_META: dict[str, dict[str, str]] = {
    "producao_por_produto": {
        "dimension": "produto",
        "entity_field": "produto",
        "value_field": "valor",
        "metric_kind": "revenue",
        "schema": SCHEMA_RANKED_LIST,
    },
    "producao_por_servico": {
        "dimension": "servico",
        "entity_field": "servico",
        "value_field": "valor",
        "metric_kind": "revenue",
        "schema": SCHEMA_RANKED_LIST,
    },
    "taxas_cartao_credito": {
        "dimension": "estabelecimento",
        "entity_field": "estabelecimento",
        "value_field": "valor",
        "metric_kind": "rate",
        "schema": SCHEMA_RANKED_LIST,
    },
    "parcelamento_de_cartao": {
        "dimension": "parcelas",
        "entity_field": "parcelas",
        "value_field": "valor",
        "metric_kind": "revenue",
        "schema": SCHEMA_RANKED_LIST,
    },
    "faturamento_por_tipo_de_venda": {
        "dimension": "tipo_de_venda",
        "entity_field": "tipo",
        "value_field": "valor",
        "metric_kind": "revenue",
        "schema": SCHEMA_RANKED_LIST,
    },
    "faturamento_tipo_venda_produtos": {
        "dimension": "tipo_venda_produtos",
        "entity_field": "tipo",
        "value_field": "valor",
        "metric_kind": "revenue",
        "schema": SCHEMA_RANKED_LIST,
    },
    "faturamento_por_tipo_de_pagamento": {
        "dimension": "forma_pagamento",
        "entity_field": "tipo",
        "value_field": "valor",
        "metric_kind": "revenue",
        "schema": SCHEMA_RANKED_LIST,
    },
    "comissao_por_concessionaria": {
        "dimension": "concessionaria",
        "entity_field": "concessionaria",
        "value_field": "valor_comissao",
        "metric_kind": "commission",
        "schema": SCHEMA_RANKED_LIST,
    },
    "comissao_por_tipo_de_os_por_concessionaria": {
        "dimension": "tipo_os",
        "entity_field": "tipo_os",
        "value_field": "valor_comissao",
        "metric_kind": "commission",
        "schema": SCHEMA_TABLE,
        "subdimension": "concessionaria",
    },
    "faturamento_liquido": {
        "dimension": "periodo",
        "entity_field": "periodo",
        "value_field": "valor",
        "metric_kind": "revenue",
        "schema": SCHEMA_SCALAR,
    },
}

# Mapeamento de dimensão canônica para chave de índice
DIMENSION_TO_INDEX_KEY: dict[str, str] = {
    "por_concessionaria": "faturamento_e_comissao_por_concessionaria",
    "por_concessionaria_tipo_os": "comissao_por_tipo_de_os_por_concessionaria",
    "por_servico": "producao_por_servico",
    "por_produto": "producao_por_produto",
    "por_vendedor": "performance_por_vendedor",
    "por_forma_pagamento": "faturamento_por_tipo_de_pagamento",
    "por_tipo_venda": "faturamento_por_tipo_de_venda",
    "por_numero_parcelas": "parcelamento_de_cartao",
    "por_empresa": "taxas_cartao_credito",
}

DIMENSION_ALIASES: dict[str, tuple[str, ...]] = {
    "forma_pagamento": ("forma_pagamento", "pagamento", "tipo_de_pagamento"),
    "tipo_de_venda": ("tipo_de_venda", "tipo_venda", "venda"),
    "tipo_venda_produtos": ("tipo_venda_produtos", "venda_produtos"),
    "servico": ("servico", "serviço", "servicos", "serviços"),
    "produto": ("produto", "produtos"),
    "concessionaria": ("concessionaria", "concessionária", "concessionarias"),
    "tipo_os": ("tipo_os", "tipo_de_os", "os"),
    "estabelecimento": ("estabelecimento", "estabelecimentos"),
    "parcelas": ("parcelas", "parcelamento"),
    "periodo": ("periodo", "período", "faturamento", "receita"),
}

METRIC_KIND_ALIASES: dict[str, tuple[str, ...]] = {
    "revenue": ("revenue", "faturamento", "receita", "valor"),
    "commission": ("commission", "comissao", "comissão", "comissoes", "comissões"),
    "share": ("share", "percentual", "participacao", "participação"),
    "count": ("count", "quantidade"),
    "rate": ("rate", "taxa", "taxas"),
}

# Padrão para detectar chaves que são nomes de entidades (nomes próprios, empresas, etc.)
# Inclui underscore para chaves já normalizadas via ``_metric_dict_key`` (ex: gwm_bamaq).
_ENTITY_KEY_PATTERN = re.compile(r"^[A-Za-zÀ-ÖØ-öø-ÿ0-9\s\-_\.\(\)|]+$")
_PLACEHOLDER_KEY_RX = re.compile(
    r"mais\s+\d+\s+linha|Omitidas\s+\d+\s+linha|Exibindo os 10 piores",
    re.IGNORECASE,
)

# theme (produtor) → chave de índice canônica quando difere do slug do theme
THEME_TO_INDEX_KEY: dict[str, str] = {
    "faturamento_por_forma_pagamento": "faturamento_por_tipo_de_pagamento",
    "faturamento_por_concessionaria": "faturamento_e_comissao_por_concessionaria",
    "comissao_por_concessionaria": "faturamento_e_comissao_por_concessionaria",
    "comissao_por_concessionaria_tipo_os": "comissao_por_tipo_de_os_por_concessionaria",
    "parcelamento_cartao": "parcelamento_de_cartao",
    "taxas_cartao_credito": "taxas_cartao_credito",
    "faturamento_por_tipo_venda": "faturamento_por_tipo_de_venda",
}


def canonical_meta_for_key(key: str) -> dict[str, str] | None:
    meta = CANONICAL_INDEX_META.get(key)
    return dict(meta) if meta else None


def _is_placeholder_key(key: str) -> bool:
    return bool(_PLACEHOLDER_KEY_RX.search(key))


def _is_flat_entity_map(data: dict[str, Any]) -> bool:
    """Detecta se o dict é um mapa plano {entidade: valor}."""
    if not data:
        return False

    # Chave de índice canônica → não é mapa plano de entidades
    if any(k in CANONICAL_INDEX_META for k in data):
        return False

    entity_count = 0
    for key, value in data.items():
        if key.startswith("_"):
            continue
        if _is_placeholder_key(key):
            continue
        if value is None:
            continue
        if _ENTITY_KEY_PATTERN.match(key):
            entity_count += 1

    eligible = sum(
        1
        for key, value in data.items()
        if not key.startswith("_")
        and not _is_placeholder_key(key)
        and value is not None
    )
    if eligible == 0:
        return False
    return entity_count > 0 and (entity_count / eligible) >= 0.5


def _filter_flat_map(data: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in data.items()
        if not key.startswith("_")
        and not _is_placeholder_key(key)
        and value is not None
    }


def _metric_sort_key(value: Any) -> float:
    try:
        return float(
            re.sub(r"[R$.,\s%]", "", str(value))
            .replace(",", ".")
            .strip()
            or "0"
        )
    except (ValueError, TypeError):
        return 0.0


def _select_head_tail_entries(
    entries: list[tuple[str, Any]],
) -> tuple[list[tuple[str, Any]], int, bool]:
    total_original = len(entries)
    sorted_entries = sorted(entries, key=lambda item: _metric_sort_key(item[1]), reverse=True)
    if total_original <= _HEAD_TAIL_FULL_THRESHOLD:
        return sorted_entries, total_original, False
    selected = (
        sorted_entries[:_HEAD_TAIL_LIMIT]
        + sorted_entries[-_HEAD_TAIL_LIMIT:]
    )
    return selected, total_original, True


def _infer_entity_field(dimension: str) -> str:
    """Infere o nome do campo de entidade a partir da dimensão."""
    dimension_map = {
        "por_concessionaria": "concessionaria",
        "por_concessionaria_tipo_os": "concessionaria",
        "por_servico": "servico",
        "por_produto": "produto",
        "por_vendedor": "vendedor",
        "por_forma_pagamento": "tipo",
        "por_tipo_venda": "tipo",
        "por_numero_parcelas": "parcelas",
        "por_empresa": "estabelecimento",
        "por_regiao": "regiao",
        "por_categoria": "categoria",
        "por_periodo": "periodo",
    }
    return dimension_map.get(dimension, "entidade")


def _consumer_metric_kind(producer_metric: str | None) -> str:
    if not producer_metric:
        return "revenue"
    normalized = producer_metric.strip().lower()
    if normalized in ("comissao", "comissão", "commission"):
        return "commission"
    if normalized in ("taxa_cartao", "taxa", "taxas", "rate"):
        return "rate"
    return "revenue"


def _resolve_index_key(
    *,
    dimension: str | None = None,
    theme: str | None = None,
) -> str | None:
    if dimension:
        index_key = DIMENSION_TO_INDEX_KEY.get(dimension)
        if index_key:
            return index_key
    if theme:
        slug = theme.strip().lower()
        if slug in CANONICAL_INDEX_META:
            return slug
        if slug in THEME_TO_INDEX_KEY:
            return THEME_TO_INDEX_KEY[slug]
    return None


def _meta_for_index(
    index_key: str,
    *,
    producer_metric: str | None = None,
    producer_dimension: str | None = None,
) -> dict[str, str]:
    meta = dict(canonical_meta_for_key(index_key) or {})
    if not meta and producer_dimension:
        entity_field = _infer_entity_field(producer_dimension)
        meta = {
            "dimension": _dimension_from_key(index_key),
            "entity_field": entity_field,
            "value_field": "valor",
            "metric_kind": "revenue",
            "schema": SCHEMA_RANKED_LIST,
        }

    consumer_kind = _consumer_metric_kind(producer_metric)
    meta["metric_kind"] = consumer_kind
    if consumer_kind == "commission":
        meta["value_field"] = "valor_comissao"
    elif consumer_kind == "rate":
        meta["value_field"] = "valor"
    elif "value_field" not in meta:
        meta["value_field"] = "valor"

    return meta


def _format_row_value(value: Any) -> str:
    """
    Formata valor de linha para ``table_rows_sample``.

    Strings passam intactas. Dict aninhado NÃO é serializado via ``str(dict)`` —
    levanta erro para forçar correção na origem (parser/prompt).
    """
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        raise ValueError(
            f"key_metrics: valor estruturado nao serializado: {value!r}"
        )
    if value is None:
        return ""
    return str(value)


def _rows_to_table_sample(
    rows: list[dict[str, Any]],
    *,
    entity_field: str,
) -> list[str]:
    """Converte rows tipadas em linhas de ``table_rows_sample`` determinísticas."""
    sample: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        entity = row.get(entity_field)
        if not isinstance(entity, str) or not entity.strip():
            for candidate in ("concessionaria", "tipo", "label", "entidade"):
                raw = row.get(candidate)
                if isinstance(raw, str) and raw.strip():
                    entity = raw
                    break
        if not isinstance(entity, str) or not entity.strip():
            continue
        cells: list[str] = []
        for field in sorted(row.keys()):
            if field == entity_field or field.startswith("_"):
                continue
            if field in {"concessionaria", "tipo", "label", "entidade"} and row.get(field) == entity:
                continue
            raw = row[field]
            if raw is None or isinstance(raw, dict):
                continue
            text = raw.strip() if isinstance(raw, str) else str(raw)
            if text:
                cells.append(f"{field}: {text}")
        sample.append(f"{entity.strip()} | {' | '.join(cells)}" if cells else entity.strip())
    return sample


def _is_canonical_table_payload(data: dict[str, Any]) -> bool:
    """Detecta ``{_meta?, rows}`` ou ``{_meta?, table_rows_sample}`` na raiz."""
    structural = {"_meta", "rows", "table_rows_sample"}
    other = [
        k for k in data
        if k not in structural and not str(k).startswith("_")
    ]
    if other:
        return False
    if "rows" in data and isinstance(data["rows"], list):
        return True
    if "table_rows_sample" in data and isinstance(data["table_rows_sample"], list):
        return True
    return False


def _wrap_canonical_table_payload(
    data: dict[str, Any],
    *,
    index_key: str,
    metric_kind: str | None = None,
    dimension: str | None = None,
) -> dict[str, Any]:
    meta = _meta_for_index(
        index_key,
        producer_metric=metric_kind,
        producer_dimension=dimension,
    )
    embedded = data.get("_meta")
    if isinstance(embedded, dict):
        for field, value in embedded.items():
            meta.setdefault(str(field), value)
    meta["schema"] = SCHEMA_TABLE

    entity_field = str(meta.get("entity_field") or "entidade")
    payload: dict[str, Any] = {"_meta": meta}

    rows = data.get("rows")
    if isinstance(rows, list):
        typed_rows = [dict(r) for r in rows if isinstance(r, dict)]
        payload["rows"] = typed_rows
        sample = _rows_to_table_sample(typed_rows, entity_field=entity_field)
        if sample:
            payload["table_rows_sample"] = sample
            meta["total_original_rows"] = len(typed_rows)
            meta["truncated_head_tail"] = False

    sample_raw = data.get("table_rows_sample")
    if isinstance(sample_raw, list) and "table_rows_sample" not in payload:
        payload["table_rows_sample"] = [str(item) for item in sample_raw if item is not None]

    logger.info(
        "key_metrics embrulhado (canonical table): index=%s, rows=%s",
        index_key,
        len(payload.get("rows") or payload.get("table_rows_sample") or []),
    )
    return {index_key: payload}


def _wrap_flat_entity_map(
    data: dict[str, Any],
    *,
    index_key: str,
    metric_kind: str | None = None,
    dimension: str | None = None,
) -> dict[str, Any]:
    """Embrulha mapa plano {entidade: valor} no formato canônico do fact engine."""
    if not data or not index_key:
        return {}

    meta = _meta_for_index(
        index_key,
        producer_metric=metric_kind,
        producer_dimension=dimension,
    )
    entity_field = meta.get("entity_field", "entidade")
    value_field = meta.get("value_field", "valor")

    entries = list(data.items())
    selected_entries, total_original_rows, truncated = _select_head_tail_entries(entries)
    meta["total_original_rows"] = total_original_rows
    meta["truncated_head_tail"] = truncated

    if meta.get("schema") == SCHEMA_TABLE:
        sample = [
            f"{entity} | {_format_row_value(value)}"
            for entity, value in selected_entries
        ]
        logger.info(
            "key_metrics embrulhado (table): index=%s, entities=%d, original=%d",
            index_key,
            len(selected_entries),
            total_original_rows,
        )
        return {index_key: {"_meta": meta, "table_rows_sample": sample}}

    rows: list[dict[str, Any]] = []
    for entity, value in selected_entries:
        row: dict[str, Any] = {entity_field: entity, value_field: value}
        if isinstance(value, str) and "(" in value and ")" in value:
            match = re.search(r"\(([0-9,.]+)%\)", value)
            if match:
                row["percentual"] = f"{match.group(1)}%"
        rows.append(row)

    logger.info(
        "key_metrics embrulhado: index=%s, dimension=%s, entities=%d, original=%d",
        index_key,
        dimension or meta.get("dimension"),
        len(selected_entries),
        total_original_rows,
    )
    return {index_key: {"_meta": meta, "rows": rows}}


def _infer_dimension_from_key(key: str) -> str | None:
    """Infere a dimensão produtor (por_*) a partir da chave de índice."""
    slug = key.lower()
    if "tipo_de_os" in slug and "concessionaria" in slug:
        return "por_concessionaria_tipo_os"
    if "concessionaria" in slug:
        return "por_concessionaria"
    if "servico" in slug:
        return "por_servico"
    if "produto" in slug:
        return "por_produto"
    if "pagamento" in slug:
        return "por_forma_pagamento"
    if "tipo_de_venda" in slug or "tipo_venda" in slug:
        return "por_tipo_venda"
    if "parcelamento" in slug or "parcelas" in slug:
        return "por_numero_parcelas"
    if "taxa" in slug:
        return "por_empresa"
    return None


def enrich_key_metrics(
    key_metrics: Mapping[str, Any],
    *,
    metric_kind: str | None = None,
    dimension: str | None = None,
    theme: str | None = None,
) -> dict[str, Any]:
    """Normaliza ``key_metrics`` do produtor com ``_meta`` canónico quando ausente."""
    if not key_metrics:
        return {}

    data = dict(key_metrics)

    # Schema canônico de tabela na raiz ({_meta, rows} / table_rows_sample)
    if _is_canonical_table_payload(data):
        index_key = _resolve_index_key(dimension=dimension, theme=theme)
        if index_key:
            return _wrap_canonical_table_payload(
                data,
                index_key=index_key,
                metric_kind=metric_kind,
                dimension=dimension,
            )

    if _is_flat_entity_map(data):
        filtered = _filter_flat_map(data)
        index_key = _resolve_index_key(dimension=dimension, theme=theme)
        if index_key and filtered:
            return _wrap_flat_entity_map(
                filtered,
                index_key=index_key,
                metric_kind=metric_kind,
                dimension=dimension,
            )

    enriched: dict[str, Any] = {}

    for key, raw in key_metrics.items():
        if key.startswith("_"):
            continue
        
        canonical = canonical_meta_for_key(key)
        
        # Caso 1: já tem _meta
        if isinstance(raw, dict) and "_meta" in raw:
            meta = dict(raw["_meta"])
            if canonical:
                for field, value in canonical.items():
                    meta.setdefault(field, value)
            payload = {k: v for k, v in raw.items() if k != "_meta"}
            # Se schema table com rows tipadas e sem sample, gera sample determinístico
            if (
                meta.get("schema") == SCHEMA_TABLE
                and isinstance(payload.get("rows"), list)
                and "table_rows_sample" not in payload
            ):
                entity_field = str(meta.get("entity_field") or "entidade")
                sample = _rows_to_table_sample(
                    [r for r in payload["rows"] if isinstance(r, dict)],
                    entity_field=entity_field,
                )
                if sample:
                    payload = {**payload, "table_rows_sample": sample}
            enriched[key] = {"_meta": meta, **payload}
            continue
        
        # Caso 2: é lista de rows
        if isinstance(raw, list):
            meta = dict(canonical) if canonical else _infer_meta_from_key(key, raw)
            enriched[key] = {"_meta": meta, "rows": raw}
            continue
        
        # Caso 3: mapa plano de entidades sob chave de índice
        if isinstance(raw, dict) and _is_flat_entity_map(raw):
            filtered = _filter_flat_map(raw)
            index_key = (
                key
                if key in CANONICAL_INDEX_META
                else _resolve_index_key(
                    dimension=dimension or _infer_dimension_from_key(key),
                    theme=theme or key,
                )
            )
            if index_key and filtered:
                enriched.update(
                    _wrap_flat_entity_map(
                        filtered,
                        index_key=index_key,
                        metric_kind=metric_kind,
                        dimension=dimension or _infer_dimension_from_key(key),
                    )
                )
                continue
        
        # Caso 4: é um valor escalar
        if isinstance(raw, (int, float)) and not isinstance(raw, bool):
            meta = dict(canonical) if canonical else {
                "dimension": "periodo",
                "entity_field": "periodo",
                "value_field": "valor",
                "metric_kind": "revenue",
                "schema": SCHEMA_SCALAR,
            }
            enriched[key] = {"_meta": meta, "value": raw}
            continue
        
        # Caso 5: table_rows_sample
        if isinstance(raw, dict) and "table_rows_sample" in raw:
            meta = dict(canonical) if canonical else _infer_meta_from_key(key, raw.get("table_rows_sample"))
            enriched[key] = {"_meta": meta, **raw}
            continue
        
        # Fallback: mantém intacto
        enriched[key] = raw
    
    return enriched


def index_identity(meta: Mapping[str, Any]) -> tuple[str, ...]:
    dimension = str(meta.get("dimension") or "")
    metric_kind = str(meta.get("metric_kind") or "")
    subdimension = meta.get("subdimension")
    if subdimension:
        return (dimension, metric_kind, str(subdimension))
    return (dimension, metric_kind)


def collect_index_identities(key_metrics: Mapping[str, Any]) -> list[tuple[str, tuple[str, ...]]]:
    identities: list[tuple[str, tuple[str, ...]]] = []
    for key, raw in key_metrics.items():
        if key.startswith("_"):
            continue
        meta = extract_meta(key, raw)
        if meta:
            identities.append((key, index_identity(meta)))
    return identities


def extract_meta(key: str, raw: Any) -> dict[str, str] | None:
    if isinstance(raw, dict):
        embedded = raw.get("_meta")
        if isinstance(embedded, dict):
            return {str(k): str(v) for k, v in embedded.items()}
    canonical = canonical_meta_for_key(key)
    if canonical:
        return dict(canonical)
    if isinstance(raw, list):
        return _infer_meta_from_key(key, raw)
    if isinstance(raw, dict) and "table_rows_sample" in raw:
        return _infer_meta_from_key(key, raw.get("table_rows_sample"))
    return None


def _infer_meta_from_key(key: str, rows: Any) -> dict[str, str]:
    canonical = canonical_meta_for_key(key)
    if canonical:
        return dict(canonical)
    entity_field = _guess_entity_field(key, rows)
    metric_kind = "commission" if "comissao" in key else "revenue"
    schema = SCHEMA_TABLE if isinstance(rows, dict) or (
        isinstance(rows, list) and rows and isinstance(rows[0], str)
    ) else SCHEMA_RANKED_LIST
    return {
        "dimension": _dimension_from_key(key),
        "entity_field": entity_field,
        "value_field": "valor_comissao" if "comissao" in key else "valor",
        "metric_kind": metric_kind,
        "schema": schema,
    }


def _dimension_from_key(key: str) -> str:
    if "servico" in key:
        return "servico"
    if "produto" in key and "tipo_venda" not in key:
        return "produto"
    if "tipo_de_pagamento" in key or "pagamento" in key:
        return "forma_pagamento"
    if "tipo_de_venda" in key:
        return "tipo_de_venda"
    if "tipo_venda_produtos" in key:
        return "tipo_venda_produtos"
    if "concessionaria" in key and "tipo_de_os" in key:
        return "tipo_os"
    if "concessionaria" in key:
        return "concessionaria"
    if "estabelecimento" in key:
        return "estabelecimento"
    if "parcelamento" in key or "parcelas" in key:
        return "parcelas"
    return key


def _guess_entity_field(key: str, rows: Any) -> str:
    if isinstance(rows, list) and rows and isinstance(rows[0], dict):
        for candidate in ("servico", "produto", "tipo", "concessionaria", "estabelecimento", "parcelas"):
            if candidate in rows[0]:
                return candidate
    if "servico" in key:
        return "servico"
    if "produto" in key:
        return "produto"
    if "concessionaria" in key:
        return "concessionaria"
    return "tipo"

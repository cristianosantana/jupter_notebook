"""
Funções de extração e coerção de campos do payload JSON retornado pelo LLM.

Responsabilidade única: receber um dict cru e extrair valores
tipados de forma segura, sem conhecimento do domínio de negócio.
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Strings
# ---------------------------------------------------------------------------

def required_str(data: dict[str, Any], key: str) -> str:
    """Extrai string obrigatória; levanta ValueError se ausente ou vazia."""
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Campo obrigatorio ausente ou invalido: {key}")
    return value.strip()


def required_str_any(data: dict[str, Any], *keys: str) -> str:
    """Extrai a primeira string não-vazia entre as chaves fornecidas."""
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    raise ValueError(f"Campo obrigatorio ausente ou invalido: {' | '.join(keys)}")


def optional_str(data: dict[str, Any], key: str) -> str | None:
    """Extrai string opcional; retorna None se ausente ou vazia."""
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"Campo deve ser string: {key}")
    return value.strip() or None


def optional_str_any(data: dict[str, Any], *keys: str) -> str | None:
    """Extrai a primeira string não-vazia entre as chaves; retorna None se nenhuma."""
    for key in keys:
        value = data.get(key)
        if value is None:
            continue
        if not isinstance(value, str):
            raise ValueError(f"Campo deve ser string: {key}")
        if value.strip():
            return value.strip()
    return None


# ---------------------------------------------------------------------------
# Texto livre (aceita str, list, int, float, bool, dict)
# ---------------------------------------------------------------------------

def optional_text(data: dict[str, Any], key: str) -> str | None:
    """
    Extrai texto opcional com coerção permissiva de tipo.

    Aceita: str, list[str], int, float, bool, dict (→ JSON compacto).
    Retorna None se ausente ou vazio.
    """
    value = data.get(key)
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, list):
        lines = [str(item).strip() for item in value if str(item).strip()]
        return "\n".join(lines) if lines else None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


# ---------------------------------------------------------------------------
# Listas de strings
# ---------------------------------------------------------------------------

def string_tuple(data: dict[str, Any], key: str) -> tuple[str, ...]:
    """Extrai lista de strings como tupla imutável."""
    value = data.get(key, [])
    if not isinstance(value, list):
        raise ValueError(f"Campo deve ser lista de strings: {key}")
    return tuple(item.strip() for item in value if isinstance(item, str) and item.strip())


def string_tuple_any(data: dict[str, Any], *keys: str) -> tuple[str, ...]:
    """Extrai a primeira lista não-vazia entre as chaves fornecidas."""
    for key in keys:
        if key in data:
            return string_tuple(data, key)
    return ()


# ---------------------------------------------------------------------------
# Dicts de métricas (aceita dict ou lista com formato variado)
# ---------------------------------------------------------------------------

def _metric_dict_key(label: str, index: int) -> str:
    normalized = unicodedata.normalize("NFKD", label.strip().lower())
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^\w]+", "_", ascii_text).strip("_")
    return slug or f"item_{index}"


# Padrão dinâmico de chaves espúrias de truncagem geradas pelo LLM:
#   "mais_21_linhas", "mais_52_itens", "mais_3_registros", etc.
_SPURIOUS_KEY_RE = re.compile(r"^mais_\d+_", re.IGNORECASE)
 
# Chaves estáticas conhecidas como metadado indevido dentro de key_metrics
_SPURIOUS_KEY_LITERALS: frozenset[str] = frozenset({
    "observacao", "observação", "nota", "note", "aviso", "warning",
    "truncado", "truncated", "resumo", "summary", "total_linhas",
    "row_count", "mais_linhas", "more_rows", "_omitidos_centro",
})
 
# Sinal textual de truncagem no valor da chave
_TRUNCATION_VALUE_RE = re.compile(
    r"mais\s+\d+\s+linha|answers\[\]\.rows|disponíveis em|"
    r"Omitidas\s+\d+\s+linha|Exibindo os 10 piores",
    re.IGNORECASE,
)
 
def _is_spurious_key(key: str) -> bool:
    k = key.strip().lower()
    return k in _SPURIOUS_KEY_LITERALS or bool(_SPURIOUS_KEY_RE.match(k))
 
 
def _is_truncated_value(value: Any) -> bool:
    if isinstance(value, str):
        return bool(_TRUNCATION_VALUE_RE.search(value))
    return False
 
 
def _parse_list_item(item: Any, index: int, result: dict[str, Any]) -> None:
    if isinstance(item, dict):
        metric = item.get("metric") or item.get("name") or item.get("label")
        if isinstance(metric, str) and metric.strip():
            entry_key = _metric_dict_key(metric, index)
            payload = {k: v for k, v in item.items() if k not in {"metric", "name", "label"}}
            result[entry_key] = (
                payload["value"]
                if (len(payload) == 1 and "value" in payload)
                else (payload or dict(item))
            )
            return
        result[f"item_{index}"] = dict(item)
        return
    if isinstance(item, str) and item.strip():
        text = item.strip()
        if ":" in text:
            label, _, rest = text.partition(":")
            result[_metric_dict_key(label, index)] = rest.strip() or text
        else:
            result[_metric_dict_key(text, index)] = text
        return
    result[f"item_{index}"] = item
 
 
def mapping(data: dict[str, Any], key: str) -> dict[str, Any]:
    """
    Extrai dict de métricas com higienização de formato.
 
    Aceita: dict direto ou lista de objetos/strings com label:valor.
 
    Remove chaves espúrias de metadado inseridas pelo LLM (mais_21_linhas,
    observacao, chaves de truncagem textual, etc.). Truncagem estrutural
    cabeça/cauda ocorre em ``enrich_key_metrics``.
    """
    value = data.get(key, {})
    if value is None:
        return {}
 
    raw: dict[str, Any] = {}
    if isinstance(value, dict):
        raw = dict(value)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _parse_list_item(item, index, raw)
    else:
        raise ValueError(f"Campo deve ser objeto JSON: {key}")
 
    clean: dict[str, Any] = {}
    for k, v in raw.items():
        if k.startswith("_"):
            logger.debug("key_metrics: chave de controle removida: %r", k)
            continue
        if _is_spurious_key(k):
            logger.debug("key_metrics: chave espuria removida: %r", k)
            continue
        if _is_truncated_value(v):
            logger.warning(
                "key_metrics: valor de truncagem na chave %r removido — dados incompletos.", k,
            )
            continue
        clean[k] = v

    return clean


# ---------------------------------------------------------------------------
# Campos numéricos e categóricos
# ---------------------------------------------------------------------------

def confidence(data: dict[str, Any]) -> str | None:
    """
    Normaliza campo confidence para 'high' | 'medium' | 'low' | None.

    Aceita string literal ou float 0–1.
    """
    value = data.get("confidence")
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, bool):
        raise ValueError("Campo deve ser string ou numero: confidence")
    if isinstance(value, (int, float)):
        score = float(value)
        if score >= 0.8:
            return "high"
        if score >= 0.5:
            return "medium"
        return "low"
    raise ValueError("Campo deve ser string ou numero: confidence")


def compression_ratio(data: dict[str, Any]) -> float | None:
    """
    Normaliza compression_ratio para float 0–1.

    Aceita: float, int, '49%', '49:1', '0.02'.
    """
    value = data.get("compression_ratio")
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("Campo deve ser numero ou string numerica: compression_ratio")
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip().replace(",", ".")
        if not text:
            return None
        if text.endswith("%"):
            return float(text[:-1].strip()) / 100.0
        if ":" in text:
            left, right = text.split(":", 1)
            denominator = float(right.strip())
            if denominator == 0:
                raise ValueError("compression_ratio nao pode ter denominador zero")
            return float(left.strip()) / denominator
        return float(text)
    raise ValueError("Campo deve ser numero ou string numerica: compression_ratio")


def coerce_state_string(value: Any, default: str) -> str:
    """
    Garante que from_state / to_state seja sempre string literal.

    O LLM às vezes retorna um objeto descritivo em vez de um nome de estado.
    Quando isso acontece, descarta e usa o default, logando um warning.
    """
    if isinstance(value, str) and value.strip():
        return value.strip()
    if value is not None:
        logger.warning(
            "campo de estado recebido como %s em vez de string — usando default %r",
            type(value).__name__,
            default,
        )
    return default

"""
Instrumentação do pipeline de analytics no chat: eventos ``pré`` / ``pós`` por etapa.

Logger dedicado: ``orion.analytics.pipeline``. Cada linha é um objecto JSON (uma
mensagem) para grep/agregação. Activar com ``ORION_ANALYTICS_PIPELINE_TRACE=true``.

Opcionalmente grava JSONL puro (uma linha = um JSON) em
``<analytics_pipeline_log_dir>/analytics_pipeline_<UTC>.jsonl`` quando o directório
está configurado (ver :class:`~orion_mcp_v3.config.settings.OrionSettings`).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from orion_mcp_v3.config.settings import OrionSettings

_LOG = logging.getLogger("orion.analytics.pipeline")

_PIPELINE_JSONL_HANDLER: logging.Handler | None = None
_PIPELINE_JSONL_PATH: Path | None = None


def configure_pipeline_file_logging(s: "OrionSettings") -> Path | None:
    """
    Se ``analytics_pipeline_trace`` e ``analytics_pipeline_log_dir`` estiverem activos,
    acrescenta um :class:`logging.FileHandler` ao logger ``orion.analytics.pipeline``
    com uma linha JSON por evento (sem envoltório de log da consola).
    """
    global _PIPELINE_JSONL_HANDLER, _PIPELINE_JSONL_PATH

    shutdown_pipeline_file_logging()

    if not s.analytics_pipeline_trace:
        return None
    raw = (s.analytics_pipeline_log_dir or "").strip()
    if not raw:
        return None

    base = Path(raw)
    if not base.is_absolute():
        base = Path.cwd() / base
    base.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = base / f"analytics_pipeline_{stamp}.jsonl"

    h = logging.FileHandler(path, mode="a", encoding="utf-8")
    h.setLevel(logging.INFO)
    h.setFormatter(logging.Formatter("%(message)s"))
    _LOG.addHandler(h)
    _LOG.setLevel(logging.INFO)
    _PIPELINE_JSONL_HANDLER = h
    _PIPELINE_JSONL_PATH = path.resolve()
    return _PIPELINE_JSONL_PATH


def shutdown_pipeline_file_logging() -> None:
    """Remove e fecha o handler JSONL (ex.: no shutdown do lifespan da app)."""
    global _PIPELINE_JSONL_HANDLER, _PIPELINE_JSONL_PATH

    if _PIPELINE_JSONL_HANDLER is None:
        return
    try:
        _LOG.removeHandler(_PIPELINE_JSONL_HANDLER)
    except ValueError:
        pass
    try:
        _PIPELINE_JSONL_HANDLER.flush()
        _PIPELINE_JSONL_HANDLER.close()
    except Exception:
        pass
    _PIPELINE_JSONL_HANDLER = None
    _PIPELINE_JSONL_PATH = None

_MAX_STR = 600
_MAX_SQL = 1200


def _truncate(s: str, max_len: int = _MAX_STR) -> str:
    s = s.replace("\n", " ").strip()
    if len(s) <= max_len:
        return s
    return s[: max_len - 3] + "..."


def _json_safe(obj: Any, depth: int = 0) -> Any:
    if depth > 6:
        return "…"
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, Mapping):
        return {str(k): _json_safe(v, depth + 1) for k, v in list(obj.items())[:40]}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(x, depth + 1) for x in obj[:50]]
    return str(obj)[:200]


def log_pipeline_event(
    *,
    etapa: str,
    fase: str,
    conversation_id: str | None = None,
    dados: Mapping[str, Any] | None = None,
) -> None:
    """Emite um evento único (JSON numa linha de log). ``fase`` ∈ {pre, post}."""
    payload: dict[str, Any] = {
        "canal": "analytics_pipeline",
        "etapa": etapa,
        "fase": fase,
    }
    if conversation_id:
        payload["conversation_id"] = conversation_id
    if dados:
        payload["dados"] = _json_safe(dict(dados))
    _LOG.info("%s", json.dumps(payload, ensure_ascii=False, default=str))


def snapshot_cognitive_plan(cp: Any) -> dict[str, Any]:
    from orion_mcp_v3.contracts.cognitive_plan import CognitivePlan

    if not isinstance(cp, CognitivePlan):
        return {"tipo": type(cp).__name__}
    hints = cp.hints or {}
    sig = hints.get("signals") if isinstance(hints, Mapping) else None
    return {
        "intent_type": cp.intent_type.value,
        "needs_analytics": cp.needs_analytics,
        "confidence": cp.confidence,
        "metrics": list(cp.metrics),
        "attention_profile": cp.attention_profile.value,
        "time_scope": cp.time_scope,
        "signals": dict(sig) if isinstance(sig, Mapping) else None,
    }


def snapshot_semantic_plan(plan: Any) -> dict[str, Any]:
    tpl = plan.hints.get("_template") if hasattr(plan, "hints") else None
    if tpl is not None:
        params = plan.hints.get("template_params") or {}
        keys = sorted(str(k) for k in params.keys())
        return {
            "intent_slug": plan.intent_slug,
            "modo": "template",
            "template_slug": getattr(tpl, "slug", None),
            "template_value_key": getattr(tpl, "value_key", None),
            "template_time_key": getattr(tpl, "time_key", None),
            "template_grain": getattr(tpl, "grain", None),
            "param_keys": keys,
        }
    hk = sorted(str(k) for k in (plan.hints or {}).keys()) if hasattr(plan, "hints") else []
    return {
        "intent_slug": plan.intent_slug,
        "modo": "compile",
        "hint_keys": hk[:32],
    }


def snapshot_analytics_result(res: Any) -> dict[str, Any]:
    rows = getattr(res, "rows", ()) or ()
    first_keys: list[str] = []
    sample_vals: dict[str, Any] = {}
    if rows and isinstance(rows[0], Mapping):
        first_keys = list(rows[0].keys())[:24]
        for k in first_keys[:6]:
            v = rows[0].get(k)
            if isinstance(v, float):
                sample_vals[k] = round(v, 4)
            else:
                sample_vals[k] = v
    sql = getattr(res, "sql", "") or ""
    plan = getattr(res, "plan", None)
    hints = getattr(plan, "hints", {}) or {}
    return {
        "intent_slug": getattr(plan, "intent_slug", None),
        "template_slug": hints.get("template_slug") if isinstance(hints, Mapping) else None,
        "row_count": getattr(res, "row_count", len(rows)),
        "sql_chars": len(sql),
        "sql_preview": _truncate(sql, _MAX_SQL),
        "first_row_keys": first_keys,
        "first_row_sample": sample_vals,
    }


def snapshot_evidence_block(eb: Any | None) -> dict[str, Any]:
    if eb is None:
        return {"presente": False}
    summary = getattr(eb, "summary", "") or ""
    metrics = getattr(eb, "metrics", {}) or {}
    return {
        "presente": True,
        "confidence": getattr(eb, "confidence", None),
        "summary_chars": len(summary),
        "summary_preview": _truncate(summary, 500),
        "metrics_value_key": metrics.get("value_key") if isinstance(metrics, Mapping) else None,
        "input_rows": metrics.get("input_rows") if isinstance(metrics, Mapping) else None,
    }


def snapshot_orchestration(orch: Any) -> dict[str, Any]:
    packed = getattr(orch, "packed_blocks", ()) or ()
    kinds: dict[str, int] = {}
    for b in packed:
        md = getattr(b, "metadata", {}) or {}
        fk = md.get("fusion_kind") if isinstance(md, Mapping) else None
        key = str(fk or "none")
        kinds[key] = kinds.get(key, 0) + 1
    pt = getattr(orch, "prompt_text", "") or ""
    fusion = getattr(orch, "fusion", None)
    n_fusion = len(getattr(fusion, "blocks", ()) or ()) if fusion is not None else 0
    return {
        "packed_block_count": len(packed),
        "fusion_kind_counts": kinds,
        "fusion_block_count": n_fusion,
        "prompt_text_chars": len(pt),
    }

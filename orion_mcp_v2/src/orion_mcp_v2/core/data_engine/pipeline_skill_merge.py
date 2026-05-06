from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from orion_mcp_v2.core.aggregators.aggregator_registry import get_aggregator

if TYPE_CHECKING:
    from orion_mcp_v2.config.settings import Settings


def _skill_aggregate_char_budget(settings: "Settings | None") -> int:
    if settings is None:
        return 6000
    eff_chars = max(2048, settings.effective_prompt_token_budget * 4)
    return min(8000, eff_chars // 4)


def _json_len(obj: Any) -> int:
    return len(json.dumps(obj, ensure_ascii=False))


def _shrink_cross_selling_aggregate(raw: dict[str, Any], budget: int) -> tuple[dict[str, Any], bool]:
    """Remove pares do fim até caber no orçamento de caracteres do JSON."""
    out = dict(raw)
    pairs = out.get("top_pairs")
    truncated = False
    if not isinstance(pairs, list):
        return out, truncated
    while pairs and _json_len(out) > budget:
        pairs = pairs[:-1]
        out["top_pairs"] = pairs
        truncated = True
    if _json_len(out) > budget:
        return {"skill_aggregate_error": "exceeds_char_budget", "budget_chars": budget}, True
    return out, truncated


def merge_skill_aggregate(
    pipeline_out: dict[str, Any],
    rows: list[dict[str, Any]],
    *,
    query_id: str | None,
    settings: "Settings | None" = None,
) -> dict[str, Any]:
    """
    Enriquece `pipeline_out` com `skill_aggregate` quando existe agregador registado.
    Reduz `top_pairs` se o JSON exceder o orçamento de caracteres.
    """
    if not query_id:
        return pipeline_out

    try:
        agg = get_aggregator(query_id)
        if agg is None:
            return pipeline_out
        raw = agg.enrich(rows)
    except ImportError:
        pipeline_out["skill_aggregate_error"] = "pandas_required_for_aggregators"
        return pipeline_out
    except ValueError as e:
        pipeline_out["skill_aggregate_error"] = str(e)
        return pipeline_out

    budget = _skill_aggregate_char_budget(settings)
    fitted, truncated = _shrink_cross_selling_aggregate(raw, budget)
    if "skill_aggregate_error" in fitted:
        pipeline_out.update(fitted)
        return pipeline_out

    pipeline_out["skill_aggregate"] = fitted
    pipeline_out["skill_aggregate_json_truncated"] = truncated
    return pipeline_out

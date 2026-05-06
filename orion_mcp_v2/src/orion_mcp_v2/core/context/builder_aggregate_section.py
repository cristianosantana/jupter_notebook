from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from orion_mcp_v2.config.settings import Settings


def _section_cap(settings: "Settings | None") -> int:
    if settings is None:
        return 6000
    eff_chars = max(2048, settings.effective_prompt_token_budget * 4)
    return min(8000, eff_chars // 4)


def format_skill_aggregate_section(
    pipeline_out: dict[str, Any],
    *,
    settings: "Settings | None" = None,
) -> str | None:
    """Bloco textual único para agregados específicos; None se não houver dados."""
    err = pipeline_out.get("skill_aggregate_error")
    agg = pipeline_out.get("skill_aggregate")
    if err and not agg:
        return "### Agregados específicos\n" + str(err)
    if not agg:
        return None

    cap = _section_cap(settings)
    body = json.dumps(agg, ensure_ascii=False)
    truncated_note = ""
    if pipeline_out.get("skill_aggregate_json_truncated"):
        truncated_note = " (lista top_pairs já foi reduzida para caber no orçamento)"
    if len(body) > cap:
        body = body[:cap] + "…"
        truncated_note += " [truncado na secção do prompt]"

    return "### Agregados específicos\n" + body + truncated_note

"""
Pipeline analítico: linhas MySQL → schema, resumo, insights e amostra (Fase 2.5).
"""

from __future__ import annotations

import statistics
from collections import Counter
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from orion_mcp_v3.broker.executor import AnalyticsResult
from orion_mcp_v3.runtime.provenance import CoverageInfo


def _type_token(val: Any) -> str:
    if val is None:
        return "unknown"
    if isinstance(val, bool):
        return "boolean"
    if isinstance(val, (int, float, Decimal)) and not isinstance(val, bool):
        return "numeric"
    if isinstance(val, (datetime, date)):
        return "timestamp"
    if isinstance(val, str):
        return "string"
    return "unknown"


def _float_mean(values: list[float]) -> float:
    return float(statistics.fmean(values))


class DataPipeline:
    """
    Transforma :class:`AnalyticsResult` em estrutura pronta para narrativa / contexto.

    Linhas são ``dict`` como devolvidos pelo cliente MySQL (DictCursor).
    """

    async def process(self, result: AnalyticsResult) -> dict[str, Any]:
        rows = result.rows
        schema = self._infer_schema(rows)
        summary = self._build_summary(rows, schema)
        insights = self._extract_insights(summary)
        sample = self._build_sample(rows)

        coverage = CoverageInfo(
            labels={
                "total_rows": result.row_count,
                "sample_rows": len(sample),
                "schema_fields": len(schema),
            },
            notes="data_pipeline_v1",
        )

        return {
            "query_text": result.plan.intent_slug,
            "sql": result.sql,
            "row_count": result.row_count,
            "schema": schema,
            "summary": summary,
            "insights": insights,
            "sample": sample,
            "coverage": coverage,
        }

    def _infer_schema(self, rows: list[dict[str, Any]]) -> dict[str, str]:
        if not rows:
            return {}

        probe = rows[: min(50, len(rows))]
        keys: set[str] = set()
        for r in probe:
            keys.update(r.keys())

        schema: dict[str, str] = {}
        for col in sorted(keys):
            for r in probe:
                if col not in r:
                    continue
                v = r[col]
                if v is None:
                    continue
                schema[col] = _type_token(v)
                break
            else:
                schema[col] = "unknown"
        return schema

    def _build_summary(
        self,
        rows: list[dict[str, Any]],
        schema: dict[str, str],
    ) -> dict[str, Any]:
        summary: dict[str, Any] = {}
        for col, typ in schema.items():
            values = [r[col] for r in rows if col in r and r[col] is not None]
            if not values:
                continue

            if typ == "numeric":
                nums: list[float] = []
                for v in values:
                    try:
                        nums.append(float(v))
                    except (TypeError, ValueError):
                        continue
                if not nums:
                    continue
                summary[col] = {
                    "media": _float_mean(nums),
                    "min": min(nums),
                    "max": max(nums),
                    "count": len(nums),
                }
            elif typ == "string":
                counts = Counter(values)
                summary[col] = {
                    "unique": len(counts),
                    "top_5": counts.most_common(5),
                }
            elif typ == "timestamp":
                summary[col] = {
                    "earliest": min(values),
                    "latest": max(values),
                }
            elif typ == "boolean":
                summary[col] = {
                    "true_count": sum(1 for v in values if v is True),
                    "false_count": sum(1 for v in values if v is False),
                    "count": len(values),
                }

        return summary

    def _extract_insights(self, summary: dict[str, Any]) -> list[str]:
        insights: list[str] = []
        for col, stats in summary.items():
            if not isinstance(stats, dict):
                continue
            if "max" not in stats or "min" not in stats:
                continue
            variance = float(stats["max"]) - float(stats["min"])
            media = float(stats.get("media") or 0.0)
            denom = media if abs(media) > 1e-12 else 1.0
            if variance > denom * 2:
                insights.append(f"⚠️ {col}: alta variância ({variance:.4g})")
        return insights

    def _build_sample(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if len(rows) <= 5:
            return [dict(r) for r in rows]

        head = [dict(r) for r in rows[:2]]
        tail = [dict(r) for r in rows[-2:]]

        numeric_cols = [
            k
            for k, v in rows[0].items()
            if isinstance(v, (int, float, Decimal)) and not isinstance(v, bool)
        ]
        outliers: list[dict[str, Any]] = []
        if numeric_cols:
            col = numeric_cols[0]

            def _key(r: dict[str, Any]) -> float:
                try:
                    return float(r.get(col) or 0)
                except (TypeError, ValueError):
                    return 0.0

            sorted_rows = sorted(rows, key=_key, reverse=True)
            outliers = [dict(sorted_rows[0])]

        return head + tail + outliers
